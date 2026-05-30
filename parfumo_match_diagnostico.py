"""
parfumo_match_diagnostico.py
Analisa sem-match do Parfumo em duas etapas rápidas:
  1. Marcas únicas do Parfumo → score contra marcas do catálogo
  2. Amostra de perfumes sem match com melhor candidato por marca+nome

Gera parfumo_marcas_sem_match.csv e parfumo_perfumes_sem_match.csv
"""
import os, re, unicodedata, collections, logging, random
import pandas as pd
from supabase import create_client
from rapidfuzz import process, fuzz
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CSV_PATH      = r"c:\Users\yurim\OneDrive\Área de Trabalho\ScentSearch\database_fragrantica\parfumo_data_clean.csv"
OUT_MARCAS    = r"c:\Users\yurim\OneDrive\Área de Trabalho\scentsearch-scraper\parfumo_marcas_sem_match.csv"
OUT_PERFUMES  = r"c:\Users\yurim\OneDrive\Área de Trabalho\scentsearch-scraper\parfumo_perfumes_sem_match.csv"

NOTE_COLS     = ["Top_Notes", "Middle_Notes", "Base_Notes"]
BRAND_THR     = 85
NAME_THR      = 75
AMOSTRA       = 500   # perfumes sem match para análise de nome


def normalize(text):
    if not text or str(text).strip().upper() in ("NA", "NAN", ""):
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()


def load_catalog(supabase):
    all_p, offset = [], 0
    while True:
        batch = supabase.table("perfumes").select("id, nome, marca").range(offset, offset+999).execute().data
        if not batch:
            break
        all_p.extend(batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Catálogo: {len(all_p):,} perfumes")
    return all_p


def tem_nota(row):
    for col in NOTE_COLS:
        v = str(row.get(col, "")).strip()
        if v and v.upper() not in ("NA", "NAN"):
            return True
    return False


def run():
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    catalog  = load_catalog(supabase)

    # Índices
    brand_groups = collections.defaultdict(list)
    for p in catalog:
        b = normalize(p["marca"] or "")
        n = normalize(p["nome"]  or "")
        if b or n:
            brand_groups[b].append({"id": p["id"], "name_norm": n, "nome": p["nome"], "marca": p["marca"]})
    brand_keys = list(brand_groups.keys())
    log.info(f"Marcas no catálogo: {len(brand_keys):,}")

    # Carrega CSV
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="latin-1")

    df_notas = df[df.apply(tem_nota, axis=1)].copy()
    log.info(f"Parfumo com pirâmide: {len(df_notas):,}")

    # ── ETAPA 1: marcas únicas do Parfumo ──────────────────────────────
    log.info("Etapa 1: analisando marcas únicas...")
    marcas_parfumo = df_notas["Brand"].dropna().unique()

    marcas_result = []
    for brand_raw in marcas_parfumo:
        par_b = normalize(brand_raw)
        if not par_b:
            continue

        if par_b in brand_groups:
            score      = 100
            match_nome = par_b
            status     = "EXATO"
        else:
            bm = process.extractOne(par_b, brand_keys, scorer=fuzz.token_set_ratio)
            if bm:
                score, match_nome = bm[1], bm[0]
                status = "OK" if score >= BRAND_THR else ("PROXIMO" if score >= 65 else "SEM_MATCH")
            else:
                score, match_nome, status = 0, "", "SEM_MATCH"

        n_perfumes = len(df_notas[df_notas["Brand"] == brand_raw])
        marcas_result.append({
            "parfumo_brand":   brand_raw,
            "melhor_match":    match_nome,
            "score":           score,
            "status":          status,
            "n_perfumes":      n_perfumes,
        })

    df_marcas = pd.DataFrame(marcas_result).sort_values("score", ascending=True)
    df_marcas.to_csv(OUT_MARCAS, index=False, encoding="utf-8-sig")

    # Resumo marcas
    total_marcas = len(df_marcas)
    for status in ["SEM_MATCH", "PROXIMO", "OK", "EXATO"]:
        sub = df_marcas[df_marcas["status"] == status]
        pct = len(sub) / total_marcas * 100
        n_perf = sub["n_perfumes"].sum()
        log.info(f"  {status:10s}: {len(sub):4d} marcas ({pct:.1f}%) → {n_perf:,} perfumes com pirâmide")

    # ── ETAPA 2: amostra de perfumes sem match de marca ─────────────────
    log.info(f"\nEtapa 2: amostrando {AMOSTRA} perfumes de marcas sem match...")

    sem_match_brands = set(
        df_marcas[df_marcas["status"].isin(["SEM_MATCH", "PROXIMO"])]["parfumo_brand"].tolist()
    )
    df_sem = df_notas[df_notas["Brand"].isin(sem_match_brands)].copy()
    amostra_rows = df_sem.sample(min(AMOSTRA, len(df_sem)), random_state=42)

    perf_result = []
    for _, row in amostra_rows.iterrows():
        par_b = normalize(row.get("Brand", ""))
        par_n = normalize(row.get("Name",  ""))
        query = f"{par_b} {par_n}".strip()

        # Só testa nome dentro da marca mais próxima (rápido)
        bm = process.extractOne(par_b, brand_keys, scorer=fuzz.token_set_ratio) if par_b else None
        nome_cand, nome_score = "", 0
        if bm:
            cands = brand_groups[bm[0]]
            name_ch = {c["id"]: c["name_norm"] for c in cands}
            nm = process.extractOne(par_n, name_ch, scorer=fuzz.token_set_ratio) if par_n else None
            if nm:
                cand_info = next((c for c in cands if c["id"] == nm[2]), {})
                nome_cand  = f"{cand_info.get('marca','')} / {cand_info.get('nome','')}"
                nome_score = nm[1]

        perf_result.append({
            "parfumo_brand":    row.get("Brand", ""),
            "parfumo_name":     row.get("Name",  ""),
            "brand_score":      bm[1] if bm else 0,
            "brand_match":      bm[0] if bm else "",
            "nome_candidato":   nome_cand,
            "nome_score":       nome_score,
        })

    df_perf = pd.DataFrame(perf_result).sort_values("brand_score", ascending=False)
    df_perf.to_csv(OUT_PERFUMES, index=False, encoding="utf-8-sig")

    log.info(f"\nArquivos gerados:")
    log.info(f"  {OUT_MARCAS}")
    log.info(f"  {OUT_PERFUMES}")
    log.info("Abra no Excel para inspecionar os casos.")


if __name__ == "__main__":
    load_dotenv()
    run()
