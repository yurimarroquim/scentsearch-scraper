"""
parfumo_campos_import.py — Importa perfumista, ano_lancamento, concentracao e acordes
do dataset Parfumo para a tabela perfumes do ScentSearch.

PRÉ-REQUISITO: executar no Supabase SQL Editor antes de rodar:
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS perfumista TEXT;
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS ano_lancamento INTEGER;
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS concentracao TEXT;
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS acordes TEXT[];

Usa o mesmo matching de 2 fases do parfumo_import.py.
"""
import os, re, time, logging, unicodedata, collections
import pandas as pd
from supabase import create_client
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CSV_PATH        = r"c:\Users\yurim\OneDrive\Área de Trabalho\ScentSearch\database_fragrantica\parfumo_data_clean.csv"
CHECKPOINT_FILE = r"c:\Users\yurim\OneDrive\Área de Trabalho\scentsearch-scraper\parfumo_campos_checkpoint.txt"

BRAND_THRESHOLD = 85
NAME_THRESHOLD  = 75
FULL_THRESHOLD  = 80
BATCH_SIZE      = 200

CONCENTRACAO_MAP = {
    "eau de parfum":   "Eau de Parfum",
    "eau de toilette": "Eau de Toilette",
    "eau de cologne":  "Eau de Cologne",
    "cologne":         "Colônia",
    "parfum":          "Parfum",
    "extrait":         "Parfum",
    "extrait de parfum": "Parfum",
    "eau fraiche":     "Eau Fraîche",
    "eau fraîche":     "Eau Fraîche",
    "body spray":      "Body Spray",
}

ACORDES_MAP = {
    "woody":       "Amadeirado",
    "floral":      "Floral",
    "citrus":      "Cítrico",
    "musky":       "Almiscarado",
    "musk":        "Almiscarado",
    "fresh":       "Fresco",
    "sweet":       "Doce",
    "spicy":       "Especiado",
    "aromatic":    "Aromático",
    "powdery":     "Atalcado",
    "green":       "Verde",
    "aquatic":     "Aquático",
    "fruity":      "Frutado",
    "leather":     "Couro",
    "gourmand":    "Gourmand",
    "earthy":      "Terroso",
    "smoky":       "Esfumaçado",
    "amber":       "Ambarado",
    "balsamic":    "Balsâmico",
    "animalic":    "Animálico",
    "vanilla":     "Baunilha",
    "warm":        "Quente",
    "soft":        "Suave",
    "rose":        "Rosa",
    "oriental":    "Oriental",
    "ozonic":      "Ozônico",
    "mossy":       "Musgoso",
}


def normalize(text):
    if not text or str(text).strip().upper() in ("NA", "NAN", ""):
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()


def traduzir_concentracao(valor):
    if not valor or str(valor).strip().upper() in ("NA", "NAN", ""):
        return None
    chave = str(valor).strip().lower()
    chave = unicodedata.normalize("NFKD", chave).encode("ascii", "ignore").decode()
    for k, v in CONCENTRACAO_MAP.items():
        if k in chave:
            return v
    return str(valor).strip()


def traduzir_acordes(valor):
    if not valor or str(valor).strip().upper() in ("NA", "NAN", ""):
        return []
    resultado = []
    for acorde in str(valor).split(","):
        acorde = acorde.strip()
        if not acorde:
            continue
        chave = acorde.lower()
        traduzido = ACORDES_MAP.get(chave, acorde)
        resultado.append(traduzido)
    return resultado


def load_catalog(supabase):
    all_perfumes = []
    offset = 0
    while True:
        batch = (
            supabase.table("perfumes")
            .select("id, nome, marca")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not batch:
            break
        all_perfumes.extend(batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Catálogo: {len(all_perfumes):,} perfumes carregados")
    return all_perfumes


def build_index(catalog):
    brand_groups = collections.defaultdict(list)
    full_choices = {}
    nome_choices = {}
    nome_word_index = collections.defaultdict(set)  # palavra → ids com essa palavra no nome

    for p in catalog:
        b = normalize(p["marca"] or "")
        n = normalize(p["nome"]  or "")
        if not b and not n:
            continue
        brand_groups[b].append({"id": p["id"], "name_norm": n})
        full_choices[p["id"]] = f"{b} {n}".strip()
        nome_choices[p["id"]] = n
        for word in n.split():
            if len(word) > 3:
                nome_word_index[word].add(p["id"])

    brand_keys = list(brand_groups.keys())
    log.info(f"Índice: {len(brand_keys):,} marcas | {len(full_choices):,} produtos")
    return brand_groups, brand_keys, full_choices, nome_choices, nome_word_index


def find_match(par_brand, par_name, brand_groups, brand_keys, full_choices, nome_choices, nome_word_index):
    candidates = None
    if par_brand and par_brand in brand_groups:
        candidates = brand_groups[par_brand]
    elif par_brand:
        bm = process.extractOne(par_brand, brand_keys, scorer=fuzz.token_set_ratio)
        if bm and bm[1] >= BRAND_THRESHOLD:
            candidates = brand_groups[bm[0]]

    if candidates and par_name:
        name_choices = {c["id"]: c["name_norm"] for c in candidates}
        nm = process.extractOne(par_name, name_choices, scorer=fuzz.token_set_ratio)
        if nm and nm[1] >= NAME_THRESHOLD:
            return nm[2], nm[1]

    # Fase 1.5: marca do Parfumo aparece dentro do nome ScentSearch
    # Resolve casos como marca="Aventus" no site mas Brand="Creed" no Parfumo
    if par_brand and par_name:
        brand_words = [w for w in par_brand.split() if len(w) > 3]
        if brand_words:
            matching_ids = None
            for word in brand_words:
                ids = nome_word_index.get(word, set())
                matching_ids = ids if matching_ids is None else matching_ids & ids
            if matching_ids:
                id_to_nome = {pid: nome_choices[pid] for pid in matching_ids if pid in nome_choices}
                nm = process.extractOne(par_name, id_to_nome, scorer=fuzz.token_set_ratio)
                if nm and nm[1] >= NAME_THRESHOLD:
                    return nm[2], nm[1]

    query = f"{par_brand} {par_name}".strip()
    if query:
        fm = process.extractOne(query, full_choices, scorer=fuzz.token_set_ratio)
        if fm and fm[1] >= FULL_THRESHOLD:
            return fm[2], fm[1]

    return None, 0


def flush_batch(supabase, batch):
    for attempt in range(5):
        try:
            supabase.rpc("bulk_update_campos", {"data": batch}).execute()
            return
        except Exception as e:
            if attempt < 4:
                wait = 2 ** attempt
                log.warning(f"Erro de rede (tentativa {attempt+1}/5), aguardando {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def tem_dado(row):
    for col in ["Perfumers", "Release_Year", "Concentration", "Main_Accords"]:
        v = str(row.get(col, "")).strip()
        if v and v.upper() not in ("NA", "NAN"):
            return True
    return False


def run():
    supabase = get_client()
    catalog  = load_catalog(supabase)
    brand_groups, brand_keys, full_choices, nome_choices, nome_word_index = build_index(catalog)

    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="latin-1")
    log.info(f"Parfumo CSV: {len(df):,} fragrâncias")

    df_com_dado = df[df.apply(tem_dado, axis=1)].copy()
    log.info(f"Com pelo menos um campo: {len(df_com_dado):,}")

    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            start_idx = int(f.read().strip())
        log.info(f"Retomando do índice {start_idx}")

    ok = sem_match = 0
    pending_batch = []

    for i, (_, row) in enumerate(df_com_dado.iterrows()):
        if i < start_idx:
            continue

        par_brand = normalize(row.get("Brand", ""))
        par_name  = normalize(row.get("Name",  ""))
        perfume_id, score = find_match(par_brand, par_name, brand_groups, brand_keys, full_choices, nome_choices, nome_word_index)

        if not perfume_id:
            sem_match += 1
            continue

        perfumista_raw = str(row.get("Perfumers", "")).strip()
        perfumista = perfumista_raw if perfumista_raw.upper() not in ("NA", "NAN", "") else None

        ano_raw = str(row.get("Release_Year", "")).strip()
        try:
            ano = int(float(ano_raw)) if ano_raw.upper() not in ("NA", "NAN", "") else None
        except (ValueError, TypeError):
            ano = None

        concentracao = traduzir_concentracao(row.get("Concentration"))
        acordes = traduzir_acordes(row.get("Main_Accords"))

        record = {"id": perfume_id}
        if perfumista:
            record["perfumista"] = perfumista
        if ano:
            record["ano_lancamento"] = ano
        if concentracao:
            record["concentracao"] = concentracao
        if acordes:
            record["acordes"] = acordes

        if len(record) == 1:
            sem_match += 1
            continue

        pending_batch.append(record)
        ok += 1

        if len(pending_batch) >= BATCH_SIZE:
            flush_batch(supabase, pending_batch)
            pending_batch = []
            log.info(f"  [{i+1}/{len(df_com_dado)}] atualizados: {ok} | sem match: {sem_match}")
            with open(CHECKPOINT_FILE, "w") as f:
                f.write(str(i))

    if pending_batch:
        flush_batch(supabase, pending_batch)

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    log.info("=" * 40)
    log.info(f"Atualizados: {ok:,}")
    log.info(f"Sem match:   {sem_match:,}")


def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("Configure SUPABASE_URL e SUPABASE_SERVICE_KEY no .env")
    return create_client(url, key)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
