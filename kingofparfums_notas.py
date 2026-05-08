import os, re, time, logging, unicodedata, sqlite3
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from rapidfuzz import process, fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
DB_PATH = "data/scentsearch.db"

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

        return {"acordes": [], "topo": topo, "coracao": coracao, "base": base}
    except Exception as e:
        log.warning(f"Erro {url}: {e}")
    return None

def save(supabase, perfume_id, data):
    supabase.table("notas_olfativas").upsert({
        "perfume_id": perfume_id,
        "topo": [n["nome"] for n in data["topo"]],
        "coracao": [n["nome"] for n in data["coracao"]],
        "base": [n["nome"] for n in data["base"]],
        "acordes": [],
    }, on_conflict="perfume_id").execute()
    for note in data["topo"] + data["coracao"] + data["base"]:
        if note["imagem_url"]:
            try:
                supabase.table("ingredientes").upsert({
                    "nome": note["nome"],
                    "slug": slugify(note["nome"]),
                    "imagem_url": note["imagem_url"],
                }, on_conflict="slug").execute()
            except: pass

def run(limit=50):
    supabase = get_client()
    catalog = []
    offset = 0
    while True:
        batch = supabase.table("perfumes").select("id,nome,marca").eq("tipo","perfume").range(offset, offset+999).execute().data
        if not batch: break
        catalog.extend(batch)
        offset += 1000
    log.info(f"Catalogo: {len(catalog)} perfumes")

    existentes = set()
    offset = 0
    while True:
        batch = supabase.table("notas_olfativas").select("perfume_id").range(offset, offset+999).execute().data
        if not batch: break
        existentes.update(r["perfume_id"] for r in batch)
        offset += 1000
    log.info(f"Ja com notas: {len(existentes)}")

    candidates = {f"{p['marca']} {p['nome']}".lower(): p["id"] for p in catalog}

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT p.name, p.brand, p.url FROM products p
        JOIN stores s ON p.store_id = s.id
        WHERE s.slug = 'kingofparfums' AND p.url IS NOT NULL
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    log.info(f"Produtos King of Parfums: {len(rows)}")

    ok = erros = sem_match = 0
    for i, (nome, marca, url) in enumerate(rows):
        query = f"{marca or ''} {nome}".lower().strip()
        result = process.extractOne(query, candidates.keys(), scorer=fuzz.token_set_ratio)
        if not result or result[1] < 75:
            sem_match += 1
            continue
        perfume_id = candidates[result[0]]
        if perfume_id in existentes:
            continue

        data = scrape_product_page(url)
        if not data or not any([data["topo"], data["coracao"], data["base"]]):
            log.warning(f"[{i+1}] Sem notas: {url}")
            erros += 1
            time.sleep(1)
            continue

        save(supabase, perfume_id, data)
        existentes.add(perfume_id)
        log.info(f"[{i+1}/{len(rows)}] OK: {nome} | topo={len(data['topo'])} coracao={len(data['coracao'])} base={len(data['base'])}")
        ok += 1
        if i % 50 == 49: supabase = get_client()
        time.sleep(1.5)

    log.info(f"Concluido: {ok} OK | {sem_match} sem match | {erros} sem notas")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run(limit=limit)
