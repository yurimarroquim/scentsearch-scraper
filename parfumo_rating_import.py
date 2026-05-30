"""
parfumo_rating_import.py — Importa Rating_Value e Rating_Count do dataset Parfumo
para as colunas rating_parfumo e rating_count_parfumo da tabela perfumes.

PRÉ-REQUISITO: executar no Supabase SQL Editor antes de rodar:
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS rating_parfumo NUMERIC;
  ALTER TABLE perfumes ADD COLUMN IF NOT EXISTS rating_count_parfumo INTEGER;

Usa o mesmo matching de 2 fases do parfumo_import.py:
  1. Fuzzy match de marca (≥ 85)
  2. Fuzzy match de nome dentro da marca (≥ 75)
  Fallback: match combinado marca+nome (≥ 80)
"""
import os, re, time, logging, unicodedata, collections
import pandas as pd
from supabase import create_client
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

CSV_PATH        = r"c:\Users\yurim\OneDrive\Área de Trabalho\ScentSearch\database_fragrantica\parfumo_data_clean.csv"
CHECKPOINT_FILE = r"c:\Users\yurim\OneDrive\Área de Trabalho\scentsearch-scraper\parfumo_rating_checkpoint.txt"

BRAND_THRESHOLD = 85
NAME_THRESHOLD  = 75
FULL_THRESHOLD  = 80
BATCH_SIZE      = 200  # upserts por lote


def normalize(text):
    if not text or str(text).strip().upper() in ("NA", "NAN", ""):
        return ""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()


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
    for p in catalog:
        b = normalize(p["marca"] or "")
        n = normalize(p["nome"]  or "")
        if not b and not n:
            continue
        brand_groups[b].append({"id": p["id"], "name_norm": n})
        full_choices[p["id"]] = f"{b} {n}".strip()
    brand_keys = list(brand_groups.keys())
    log.info(f"Índice: {len(brand_keys):,} marcas | {len(full_choices):,} produtos")
    return brand_groups, brand_keys, full_choices


def find_match(par_brand, par_name, brand_groups, brand_keys, full_choices):
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

    query = f"{par_brand} {par_name}".strip()
    if query:
        fm = process.extractOne(query, full_choices, scorer=fuzz.token_set_ratio)
        if fm and fm[1] >= FULL_THRESHOLD:
            return fm[2], fm[1]

    return None, 0


def flush_batch(supabase, batch):
    import json
    for attempt in range(5):
        try:
            supabase.rpc("bulk_update_ratings", {"data": batch}).execute()
            return
        except Exception as e:
            if attempt < 4:
                wait = 2 ** attempt
                log.warning(f"Erro de rede (tentativa {attempt+1}/5), aguardando {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def run():
    supabase = get_client()
    catalog  = load_catalog(supabase)
    brand_groups, brand_keys, full_choices = build_index(catalog)

    try:
        df = pd.read_csv(CSV_PATH, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding="latin-1")
    log.info(f"Parfumo CSV: {len(df):,} fragrâncias")

    # Filtra apenas linhas com rating válido
    df_rated = df[
        df["Rating_Value"].notna() &
        (df["Rating_Value"].astype(str).str.upper() != "NA") &
        (df["Rating_Value"].astype(str).str.strip() != "")
    ].copy()
    log.info(f"Com rating: {len(df_rated):,}")

    # Checkpoint
    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            start_idx = int(f.read().strip())
        log.info(f"Retomando do índice {start_idx}")

    ok = sem_match = 0
    pending_batch = []

    for i, (_, row) in enumerate(df_rated.iterrows()):
        if i < start_idx:
            continue

        par_brand = normalize(row.get("Brand", ""))
        par_name  = normalize(row.get("Name",  ""))
        perfume_id, score = find_match(par_brand, par_name, brand_groups, brand_keys, full_choices)

        if not perfume_id:
            sem_match += 1
            continue

        try:
            rating_val   = float(str(row["Rating_Value"]).replace(",", "."))
            rating_count_raw = str(row.get("Rating_Count", "")).strip()
            rating_count = int(float(rating_count_raw)) if rating_count_raw.upper() not in ("NA", "NAN", "") else None
        except (ValueError, TypeError):
            sem_match += 1
            continue

        pending_batch.append({
            "id": perfume_id,
            "rating_parfumo": rating_val,
            "rating_count_parfumo": rating_count,
        })
        ok += 1

        if len(pending_batch) >= BATCH_SIZE:
            flush_batch(supabase, pending_batch)
            pending_batch = []
            log.info(f"  [{i+1}/{len(df_rated)}] atualizados: {ok} | sem match: {sem_match}")
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
