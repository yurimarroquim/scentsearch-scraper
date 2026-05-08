"""
kingofparfums_full.py — Varre TODO o catálogo da King of Parfums e extrai notas olfativas
Não depende do SQLite — descobre produtos diretamente do site (178 páginas, ~3560 produtos)
"""
import os, re, time, logging, unicodedata
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
BASE_URL = "https://www.thekingofparfums.com.br"
TOTAL_PAGES = 178


def get_client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def crawl_catalog():
    """Varre todas as páginas do catálogo e retorna lista de URLs únicas de produtos."""
    urls = []
    seen = set()
    for page in range(1, TOTAL_PAGES + 1):
        url = f"{BASE_URL}/produtos/" if page == 1 else f"{BASE_URL}/produtos/page/{page}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            page_urls = []
            for link in soup.select("a[href*='/produtos/']"):
                href = link.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = BASE_URL + href
                if "/page/" in href or href.rstrip("/").endswith("/produtos"):
                    continue
                if href not in seen:
                    seen.add(href)
                    page_urls.append(href)
            urls.extend(page_urls)
            log.info(f"Catálogo página {page}/{TOTAL_PAGES}: {len(page_urls)} produtos | total={len(urls)}")
        except Exception as e:
            log.warning(f"Erro na página {page}: {e}")
        time.sleep(1.2)
    return urls


def scrape_product_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Nome
        h1 = soup.select_one("h1.product_title, h1")
        nome = h1.get_text(strip=True) if h1 else ""

        # Marca
        marca = ""
        for sel in [".brand", "[class*='brand']", ".posted_in a", "[rel='tag']"]:
            el = soup.select_one(sel)
            if el:
                marca = el.get_text(strip=True)
                break

        # Notas olfativas
        desc_div = soup.select_one("div[data-store^='product-description']")
        if not desc_div:
            desc_div = soup.select_one(".woocommerce-product-details__short-description, .entry-content")

        topo, coracao, base = [], [], []
        if desc_div:
            current = None
            seen_names = set()
            for el in desc_div.find_all(["h4", "div"], recursive=True):
                if el.name == "h4":
                    txt = el.get_text(strip=True).lower()
                    if "topo" in txt or "saída" in txt or "saida" in txt:
                        current = "topo"
                    elif "coração" in txt or "coracao" in txt or "meio" in txt:
                        current = "coracao"
                    elif "base" in txt or "fundo" in txt:
                        current = "base"
                    continue
                if current is None:
                    continue
                img = el.find("img")
                child_divs = el.find_all("div", recursive=False)
                name_div = child_divs[-1] if len(child_divs) >= 2 else None
                if not img or not name_div:
                    continue
                name = name_div.get_text(strip=True)
                src = img.get("src", "")
                if not name or len(name) < 2 or not src.startswith("http") or name in seen_names:
                    continue
                seen_names.add(name)
                entry = {"nome": name, "imagem_url": src}
                if current == "topo":
                    topo.append(entry)
                elif current == "coracao":
                    coracao.append(entry)
                elif current == "base":
                    base.append(entry)

        return {"nome": nome, "marca": marca, "topo": topo, "coracao": coracao, "base": base}
    except Exception as e:
        log.warning(f"Erro ao scrape {url}: {e}")
    return None


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


def match_perfume(nome, marca, catalog):
    query = f"{marca} {nome}".strip()
    choices = {p["id"]: f"{p['marca']} {p['nome']}" for p in catalog}
    result = process.extractOne(query, choices, scorer=fuzz.token_set_ratio)
    if result and result[1] >= 75:
        return result[2]
    return None


def save_notas(supabase, perfume_id, data):
    supabase.table("notas_olfativas").upsert({
        "perfume_id": perfume_id,
        "topo": [n["nome"] for n in data["topo"]],
        "coracao": [n["nome"] for n in data["coracao"]],
        "base": [n["nome"] for n in data["base"]],
        "acordes": [],
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

    urls = crawl_catalog()
    log.info(f"URLs coletadas do site: {len(urls)}")

    ok, sem_match, sem_notas, ja_tem, erros = 0, 0, 0, 0, 0

    for i, url in enumerate(urls):
        data = scrape_product_page(url)
        if not data:
            erros += 1
            time.sleep(2)
            continue

        if not data["topo"] and not data["coracao"] and not data["base"]:
            sem_notas += 1
            time.sleep(1.5)
            continue

        perfume_id = match_perfume(data["nome"], data["marca"], catalog)
        if not perfume_id:
            sem_match += 1
            time.sleep(1.5)
            continue

        if perfume_id not in pendentes_ids:
            ja_tem += 1
            time.sleep(1)
            continue

        save_notas(supabase, perfume_id, data)
        pendentes_ids.discard(perfume_id)
        ok += 1

        if ok % 100 == 0:
            supabase = get_client()

        log.info(f"[{i+1}/{len(urls)}] OK: {data['marca']} {data['nome']} | T={len(data['topo'])} C={len(data['coracao'])} B={len(data['base'])}")
        time.sleep(2)

    log.info(f"Concluído: {ok} salvos | {ja_tem} já tinham | {sem_match} sem match | {sem_notas} sem notas | {erros} erros")


if __name__ == "__main__":
    run()
