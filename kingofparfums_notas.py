"""
kingofparfums_notas.py — Extrai pirâmide olfativa do King of Parfums (Nuvemshop).
Popula notas_olfativas e ingredientes (com imagens reais do CDN Fragrantica).
Roda no Replit onde o SQLite está disponível.
"""
import os, re, time, logging, unicodedata, sqlite3
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
DB_PATH          = "data/scentsearch.db"
CHECKPOINT_FILE  = "kingofparfums_notas_checkpoint.txt"
STORE_SLUG       = "kingofparfums"


def get_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def scrape_product_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, "html.parser")

        desc_div = soup.select_one("div[data-store^='product-description']")
        if not desc_div:
            return None

        topo, coracao, base = [], [], []

        for h4 in desc_div.find_all("h4"):
            label = h4.get_text(strip=True).lower()
            if "topo" in label or "sa" in label:
                target = topo
            elif "cora" in label:
                target = coracao
            elif "base" in label or "fundo" in label:
                target = base
            else:
                continue

            sib = h4.next_sibling
            while sib and not (hasattr(sib, "name") and sib.name == "div"):
                sib = sib.next_sibling
            if not sib:
                continue

            seen_names = set()
            for note_div in sib.find_all("div", recursive=True):
                children = note_div.find_all("div", recursive=False)
                if len(children) != 2:
                    continue
                img = children[0].find("img")
                name = children[1].get_text(strip=True)
                src = img.get("src", "") if img else ""
                if not img or not name or len(name) < 2 or not src.startswith("http"):
                    continue
                if name in seen_names:
                    continue
                seen_names.add(name)
                target.append({"nome": name, "imagem_url": src})

        return {"topo": topo, "coracao": coracao, "base": base}
    except Exception as e:
        log.warning(f"Erro {url}: {e}")
    return None


def save(supabase, perfume_id, data):
    supabase.table("notas_olfativas").upsert({
        "perfume_id": perfume_id,
        "topo":    [n["nome"] for n in data["topo"]],
        "coracao": [n["nome"] for n in data["coracao"]],
        "base":    [n["nome"] for n in data["base"]],
        "acordes": [],
    }, on_conflict="perfume_id").execute()

    for note in data["topo"] + data["coracao"] + data["base"]:
        if note["imagem_url"]:
            try:
                supabase.table("ingredientes").upsert({
                    "nome":       note["nome"],
                    "slug":       slugify(note["nome"]),
                    "imagem_url": note["imagem_url"],
                }, on_conflict="slug").execute()
            except Exception:
                pass


def run():
    supabase = get_client()

    # Carrega catálogo Supabase
    catalog, offset = [], 0
    while True:
        batch = supabase.table("perfumes").select("id,nome,marca").range(offset, offset + 999).execute().data
        if not batch:
            break
        catalog.extend(batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Catálogo: {len(catalog):,} perfumes")

    # Perfumes já com notas
    existentes, offset = set(), 0
    while True:
        batch = supabase.table("notas_olfativas").select("perfume_id").range(offset, offset + 999).execute().data
        if not batch:
            break
        existentes.update(r["perfume_id"] for r in batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Já com notas: {len(existentes):,}")

    candidates = {f"{p['marca']} {p['nome']}".lower(): p["id"] for p in catalog}

    # Produtos do SQLite
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT p.name, p.brand, p.url FROM products p
        JOIN stores s ON p.store_id = s.id
        WHERE s.slug = ? AND p.url IS NOT NULL
    """, (STORE_SLUG,)).fetchall()
    conn.close()
    log.info(f"Produtos {STORE_SLUG}: {len(rows):,}")

    # Checkpoint
    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            start_idx = int(f.read().strip())
        log.info(f"Retomando do índice {start_idx}")

    ok = erros = sem_match = ja_tem = 0

    for i, (nome, marca, url) in enumerate(rows):
        if i < start_idx:
            continue

        query  = f"{marca or ''} {nome}".lower().strip()
        result = process.extractOne(query, candidates.keys(), scorer=fuzz.token_set_ratio)
        if not result or result[1] < 75:
            sem_match += 1
            continue

        perfume_id = candidates[result[0]]
        if perfume_id in existentes:
            ja_tem += 1
            continue

        data = scrape_product_page(url)
        if not data or not any([data["topo"], data["coracao"], data["base"]]):
            erros += 1
            time.sleep(1)
            continue

        save(supabase, perfume_id, data)
        existentes.add(perfume_id)
        ok += 1

        if ok % 50 == 0:
            log.info(f"  [{i+1}/{len(rows)}] ok: {ok} | ja_tem: {ja_tem} | sem_match: {sem_match} | erros: {erros}")
            with open(CHECKPOINT_FILE, "w") as f:
                f.write(str(i))
            supabase = get_client()

        time.sleep(1.5)

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    log.info("=" * 40)
    log.info(f"Salvos:     {ok:,}")
    log.info(f"Já tinham:  {ja_tem:,}")
    log.info(f"Sem match:  {sem_match:,}")
    log.info(f"Sem notas:  {erros:,}")


if __name__ == "__main__":
    run()
