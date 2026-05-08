"""
pequi_notas.py — Extrai notas olfativas do Pequi Perfumes (Nuvemshop)
Usa URLs já no SQLite (store_id=12). Estrutura HTML idêntica à King of Parfums.
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
    "Accept-Language": "pt-BR,pt;q=0.9"
}
DB_PATH = "/home/runner/workspace/artifacts/scentsearch-scraper/data/scentsearch.db"
STORE_ID = 12  # Pequi Perfumes


def get_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_sqlite_products():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT p.name, p.brand, p.url FROM products p WHERE p.store_id=?",
        (STORE_ID,)
    ).fetchall()
    conn.close()
    return [{"name": r[0], "brand": r[1] or "", "url": r[2]} for r in rows]


def load_catalog(supabase):
    all_perfumes = []
    offset = 0
    while True:
        batch = supabase.table("perfumes").select("id, nome, marca").range(offset, offset + 999).execute().data
        if not batch:
            break
        all_perfumes.extend(batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Catálogo Supabase: {len(all_perfumes)} perfumes")
    return all_perfumes


def load_existentes(supabase):
    existentes = set()
    offset = 0
    while True:
        batch = supabase.table("notas_olfativas").select("perfume_id").range(offset, offset + 999).execute().data
        if not batch:
            break
        existentes.update(r["perfume_id"] for r in batch)
        offset += 1000
        if len(batch) < 1000:
            break
    log.info(f"Já com notas: {len(existentes)} perfumes")
    return existentes


def match_perfume(name, brand, catalog):
    query = f"{brand} {name}".strip()
    choices = {p["id"]: f"{p['marca']} {p['nome']}" for p in catalog}
    result = process.extractOne(query, choices, scorer=fuzz.token_set_ratio)
    if result and result[1] >= 75:
        return result[2]
    return None


def scrape_product_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content, "html.parser")

        desc = soup.select_one(".product-description, .description, [class*=desc]")
        if not desc:
            return None

        acordes = []
        for box in desc.select("div.accord-box"):
            bar = box.select_one("div.accord-bar")
            if bar and bar.get_text(strip=True):
                acordes.append(bar.get_text(strip=True))

        topo, coracao, base = [], [], []

        for h4 in desc.find_all("h4"):
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

        return {"topo": topo, "coracao": coracao, "base": base, "acordes": acordes}
    except Exception as e:
        log.warning(f"Erro ao scrape {url}: {e}")
    return None

def save_notas(supabase, perfume_id, data):
    supabase.table("notas_olfativas").upsert({
        "perfume_id": perfume_id,
        "topo": [n["nome"] for n in data["topo"]],
        "coracao": [n["nome"] for n in data["coracao"]],
        "base": [n["nome"] for n in data["base"]],
        "acordes": data["acordes"],
    }, on_conflict="perfume_id").execute()

    for note in data["topo"] + data["coracao"] + data["base"]:
        if note["nome"] and note["imagem_url"]:
            try:
                supabase.table("ingredientes").upsert({
                    "nome": note["nome"],
                    "slug": slugify(note["nome"]),
                    "imagem_url": note["imagem_url"],
                }, on_conflict="slug").execute()
            except Exception:
                pass


def run():
    supabase = get_client()

    catalog = load_catalog(supabase)
    existentes = load_existentes(supabase)
    pendentes_ids = {p["id"] for p in catalog if p["id"] not in existentes}
    log.info(f"Pendentes sem notas: {len(pendentes_ids)}")

    produtos = load_sqlite_products()
    log.info(f"Produtos Pequi no SQLite: {len(produtos)}")

    ok, sem_match, sem_notas, ja_tem, erros = 0, 0, 0, 0, 0

    for i, prod in enumerate(produtos):
        perfume_id = match_perfume(prod["name"], prod["brand"], catalog)
        if not perfume_id:
            sem_match += 1
            continue

        if perfume_id not in pendentes_ids:
            ja_tem += 1
            continue

        data = scrape_product_page(prod["url"])
        if not data:
            erros += 1
            time.sleep(2)
            continue

        if not data["topo"] and not data["coracao"] and not data["base"]:
            sem_notas += 1
            time.sleep(1.5)
            continue

        save_notas(supabase, perfume_id, data)
        pendentes_ids.discard(perfume_id)
        ok += 1

        if ok % 100 == 0:
            supabase = get_client()

        log.info(f"[{i+1}/{len(produtos)}] OK: {prod['brand']} {prod['name']} | T={len(data['topo'])} C={len(data['coracao'])} B={len(data['base'])} acordes={len(data['acordes'])}")
        time.sleep(2)

    log.info(f"Concluído: {ok} salvos | {ja_tem} já tinham | {sem_match} sem match | {sem_notas} sem notas | {erros} erros")


if __name__ == "__main__":
    run()
