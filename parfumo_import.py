"""
parfumo_import.py — Importa pirâmide olfativa do dataset Parfumo para o banco ScentSearch.

Estratégia de matching (2 fases):
  1. Filtra candidatos pela marca (fuzzy ≥ 85)
  2. Dentro da marca, faz match pelo nome (token_set_ratio ≥ 75)
  Fallback: match combinado marca+nome (≥ 80) se a marca não for encontrada.

Usa nome/marca (sempre preenchidos) em vez de nome_normalizado/marca_normalizada.
"""
import os, re, time, logging, unicodedata, collections
import pandas as pd
from supabase import create_client
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CSV_PATH       = r"c:\Users\yurim\OneDrive\Área de Trabalho\ScentSearch\database_fragrantica\parfumo_data_clean.csv"
CHECKPOINT_FILE = r"c:\Users\yurim\OneDrive\Área de Trabalho\scentsearch-scraper\parfumo_checkpoint.txt"

BRAND_THRESHOLD = 85   # score mínimo para aceitar match de marca
NAME_THRESHOLD  = 75   # score mínimo para aceitar match de nome (dentro da marca)
FULL_THRESHOLD  = 80   # score mínimo para o fallback marca+nome combinado


def normalize(text):
    if not text or str(text).strip().upper() in ("NA", "NAN", ""):
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()


def parse_notes(value):
    if not value or str(value).strip().upper() in ("NA", "NAN"):
        return []
    return [n.strip() for n in str(value).split(",") if n.strip()]


def load_catalog(supabase):
    """Carrega todos os perfumes do banco usando nome e marca (sempre preenchidos)."""
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


def load_existentes(supabase):
    existentes = set()
    offset = 0
    while True:
        batch = (
            supabase.table("notas_olfativas")
            .select("perfume_id")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not batch:
            break
        existentes.update(r["perfume_id"] for r in batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Já com notas: {len(existentes):,} perfumes")
    return existentes


def build_index(catalog):
    brand_groups = collections.defaultdict(list)
    full_choices = {}
    nome_choices = {}
    nome_word_index = collections.defaultdict(set)

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
    """Retorna (perfume_id, score) ou (None, 0)."""

    # --- Fase 1: encontrar a marca no catálogo ---
    candidates = None

    if par_brand and par_brand in brand_groups:
        candidates = brand_groups[par_brand]
    elif par_brand:
        bm = process.extractOne(par_brand, brand_keys, scorer=fuzz.token_set_ratio)
        if bm and bm[1] >= BRAND_THRESHOLD:
            candidates = brand_groups[bm[0]]

    # --- Fase 2: match de nome dentro da marca ---
    if candidates and par_name:
        name_choices = {c["id"]: c["name_norm"] for c in candidates}
        nm = process.extractOne(par_name, name_choices, scorer=fuzz.token_set_ratio)
        if nm and nm[1] >= NAME_THRESHOLD:
            return nm[2], nm[1]

    # --- Fase 1.5: marca do Parfumo aparece dentro do nome ScentSearch ---
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

    # --- Fallback: match combinado ---
    query = f"{par_brand} {par_name}".strip()
    if query:
        fm = process.extractOne(query, full_choices, scorer=fuzz.token_set_ratio)
        if fm and fm[1] >= FULL_THRESHOLD:
            return fm[2], fm[1]

    return None, 0


def run():
    supabase   = get_client()
    catalog    = load_catalog(supabase)
    existentes = load_existentes(supabase)

    brand_groups, brand_keys, full_choices, nome_choices, nome_word_index = build_index(catalog)

    # Lê CSV — tenta UTF-8 primeiro, depois latin-1
    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="latin-1")
    log.info(f"Parfumo CSV: {len(df):,} fragrâncias")

    def tem_nota(row):
        for col in ["Top_Notes", "Middle_Notes", "Base_Notes"]:
            v = str(row.get(col, "")).strip()
            if v and v.upper() not in ("NA", "NAN"):
                return True
        return False

    df_com_notas = df[df.apply(tem_nota, axis=1)].copy()
    log.info(f"Com pelo menos uma nota: {len(df_com_notas):,}")

    # Checkpoint
    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            start_idx = int(f.read().strip())
        log.info(f"Retomando do índice {start_idx}")

    ok = sem_match = ja_tem = sem_notas = 0

    for i, (_, row) in enumerate(df_com_notas.iterrows()):
        if i < start_idx:
            continue

        topo    = parse_notes(row.get("Top_Notes"))
        coracao = parse_notes(row.get("Middle_Notes"))
        base    = parse_notes(row.get("Base_Notes"))
        acordes = parse_notes(row.get("Main_Accords"))

        if not topo and not coracao and not base:
            sem_notas += 1
            continue

        par_brand = normalize(row.get("Brand", ""))
        par_name  = normalize(row.get("Name",  ""))

        perfume_id, score = find_match(par_brand, par_name, brand_groups, brand_keys, full_choices, nome_choices, nome_word_index)

        if not perfume_id:
            sem_match += 1
            continue

        if perfume_id in existentes:
            ja_tem += 1
            continue

        for attempt in range(5):
            try:
                supabase.table("notas_olfativas").upsert(
                    {
                        "perfume_id": perfume_id,
                        "topo":    topo,
                        "coracao": coracao,
                        "base":    base,
                        "acordes": acordes,
                    },
                    on_conflict="perfume_id",
                ).execute()
                break
            except Exception as e:
                if attempt < 4:
                    wait = 2 ** attempt
                    log.warning(f"Erro de rede (tentativa {attempt+1}/5), aguardando {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise

        existentes.add(perfume_id)
        ok += 1

        if ok % 200 == 0:
            log.info(f"  [{i+1}/{len(df_com_notas)}] inseridos: {ok} | sem match: {sem_match} | já tinham: {ja_tem}")
            with open(CHECKPOINT_FILE, "w") as f:
                f.write(str(i))

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    log.info("=" * 40)
    log.info(f"Inseridos:  {ok:,}")
    log.info(f"Já tinham:  {ja_tem:,}")
    log.info(f"Sem match:  {sem_match:,}")
    log.info(f"Sem notas:  {sem_notas:,}")


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
