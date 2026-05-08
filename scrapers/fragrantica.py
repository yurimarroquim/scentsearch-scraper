"""
fragrantica_scraper.py
"""
import os, re, time, logging, unicodedata
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
SEARCH_URL = "https://www.fragrantica.com.br/search/"

def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

def search_fragrantica(nome, marca):
    query = f"{marca} {nome}"
    try:
        r = cf_requests.get(SEARCH_URL, params={"query": query}, headers=HEADERS, impersonate="chrome120", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.select_one("div.cell.card.fr-news-box a[href*='/perfume/']")
        if link:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = "https://www.fragrantica.com.br" + href
            return href
    except Exception as e:
        log.warning(f"Erro busca: {e}")
    return None

def scrape_perfume_page(url):
    try:
        r = cf_requests.get(url, headers=HEADERS, impersonate="chrome120", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        acordes = [s.text.strip() for box in soup.select("div.cell.accord-box") for s in [box.select_one("span")] if s and s.text.strip()]
        topo, coracao, base = [], [], []
        pyramid = soup.select_one("#pyramid") or soup.select_one(".fragrance-notes")
        if pyramid:
            current = None
            for el in pyramid.find_all(True, recursive=True):
                txt = el.get_text(strip=True).lower()
                if "topo" in txt or "saída" in txt: current = "topo"
                elif "coração" in txt or "meio" in txt: current = "coracao"
                elif "base" in txt or "fundo" in txt: current = "base"
                for img in el.select("img"):
                    name = img.get("title") or img.get("alt") or ""
                    src = img.get("src", "")
                    if name and current:
                        entry = {"nome": name, "imagem_url": src or None}
                        if current == "topo": topo.append(entry)
                        elif current == "coracao": coracao.append(entry)
                        elif current == "base": base.append(entry)
        return {"acordes": acordes, "topo": topo, "coracao": coracao, "base": base}
    except Exception as e:
        log.warning(f"Erro scrape {url}: {e}")
    return None

def save_to_supabase(supabase, perfume_id, data):
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
                supabase.table("ingredientes").upsert({"nome": note["nome"], "slug": slugify(note["nome"]), "imagem_url": note["imagem_url"]}, on_conflict="slug").execute()
            except: pass

def run(limit=0, offset=0):
    supabase = get_client()
    query = supabase.table("perfumes").select("id,nome,marca").eq("tipo","perfume")
    if limit: query = query.range(offset, offset+limit-1)
    perfumes = query.execute().data
    existentes = {r["perfume_id"] for r in supabase.table("notas_olfativas").select("perfume_id").execute().data}
    pendentes = [p for p in perfumes if p["id"] not in existentes]
    log.info(f"Pendentes: {len(pendentes)}")
    ok = erros = nao_encontrados = 0
    for i, p in enumerate(pendentes):
        url = search_fragrantica(p["nome"], p["marca"])
        if not url:
            log.warning(f"[{i+1}] Nao encontrado: {p['marca']} {p['nome']}")
            nao_encontrados += 1
            time.sleep(2)
            continue
        data = scrape_perfume_page(url)
        if not data or not any([data["topo"], data["coracao"], data["base"], data["acordes"]]):
            log.warning(f"[{i+1}] Sem dados: {url}")
            erros += 1
            time.sleep(2)
            continue
        save_to_supabase(supabase, p["id"], data)
        log.info(f"[{i+1}/{len(pendentes)}] OK: {p['marca']} {p['nome']} | acordes={len(data['acordes'])} topo={len(data['topo'])}")
        ok += 1
        if i % 100 == 99: supabase = get_client()
        time.sleep(2.5)
    log.info(f"Concluido: {ok} OK | {nao_encontrados} nao encontrados | {erros} erros")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    run(limit=limit, offset=offset)
