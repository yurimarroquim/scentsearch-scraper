"""
Sync com fuzzy matching: casa produtos do SQLite com perfumes do catálogo Supabase
e insere preços usando o slug correto do catálogo.
"""

import os, re, logging, time, sqlite3
from rapidfuzz import fuzz, process
from supabase import create_client
import requests
from urllib.parse import quote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/home/runner/workspace/sync_match.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
API_URL = os.environ.get("LOVABLE_API_URL", "https://scentsearch.com.br")
API_KEY = os.environ.get("LOVABLE_API_KEY", "")
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

PURE_DECANT_SLUGS = {"kingofDecants", "bhdecants", "decantslondrina"}
AFFILIATE_MIDS = {"opaque": "47714"}
RAKUTEN_ID = "bvmD8pUGdGc"

def make_deeplink(store_slug, url):
    mid = AFFILIATE_MIDS.get(store_slug)
    if mid:
        return f"https://click.linksynergy.com/deeplink?id={RAKUTEN_ID}&mid={mid}&murl={quote(url, safe='')}"
    return url

def get_tipo(store_slug, name, url):
    """Determina se o produto é frasco ou decant por loja e por nome/URL."""
    if store_slug in PURE_DECANT_SLUGS:
        return "decant"
    if "decant" in name.lower() or "decant" in url.lower():
        return "decant"
    return "frasco"

def clean_name(nome, marca=""):
    nome = nome.strip()
    nome = re.sub(
        r"^(perfume|decant[aã]o?)\s+(masculino|feminino|unissex|infantil)?\s*[-–]?\s*",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    if marca:
        nome = re.sub(rf"^{re.escape(marca)}\s*[-–]?\s*", "", nome, flags=re.IGNORECASE)
    nome = re.sub(r"\s*[-–]?\s*\d+[\.,]?\d*\s*ml\b.*$", "", nome, flags=re.IGNORECASE)
    nome = re.sub(
        r"\s+(edt|edp|eau\s+de\s+(parfum|toilette|cologne))\b.*$",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    return nome.strip(" -–")

def load_catalog():
    log.info("Carregando catálogo do Supabase...")
    all_perfumes = []
    offset = 0
    while True:
        r = (
            sb.table("perfumes")
            .select("id,slug,nome,marca,tipo")
            .order("id").limit(1000).offset(offset)
            .execute()
        )
        if not r.data:
            break
        all_perfumes.extend(r.data)
        offset += 1000
        if len(r.data) < 1000:
            break
    log.info(f"Catálogo: {len(all_perfumes):,} perfumes carregados")
    return all_perfumes

def build_indexes(catalog):
    frasco_index = {}
    decant_index = {}
    for p in catalog:
        key = f"{p['marca']} {p['nome']}".lower().strip()
        if p["tipo"] == "decant":
            decant_index[key] = p["slug"]
        else:
            frasco_index[key] = p["slug"]
    return frasco_index, decant_index

def find_slug(nome, marca, index, catalog, threshold=80):
    clean = clean_name(nome, marca)
    query = f"{marca} {clean}".lower().strip()
    result = process.extractOne(query, index.keys(), scorer=fuzz.token_set_ratio)
    if result and result[1] >= threshold:
        return index[result[0]], result[1]
    return None, 0

def send_price(slug, store_name, price, url, store_slug, tipo):
    try:
        r = requests.post(
            f"{API_URL}/api/ingest/precos",
            json={
                "perfume_slug": slug,
                "loja": store_name,
                "preco": float(price),
                "link_afiliado": make_deeplink(store_slug, url),
                "disponivel": True,
                "tipo": tipo,
            },
            headers=HEADERS,
            timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        log.warning(f"Erro ao enviar preço: {e}")
        return False

def run():
    catalog = load_catalog()
    frasco_index, decant_index = build_indexes(catalog)

    conn = sqlite3.connect(
        "/home/runner/workspace/artifacts/scentsearch-scraper/data/scentsearch.db"
    )
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.name, p.brand, p.url, s.name as store_name, s.slug as store_slug, pr.price
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN prices pr ON pr.product_id = p.id
        WHERE pr.id = (SELECT id FROM prices WHERE product_id = p.id ORDER BY scraped_at DESC LIMIT 1)
        AND pr.in_stock = 1 AND pr.price > 0
    """)
    rows = cur.fetchall()
    log.info(f"Produtos a processar: {len(rows):,}")

    matched = 0
    unmatched = 0
    sent = 0
    erros = 0

    SKIP_WORDS = [
        "coffret",
        "kit",
        "body lotion",
        "loção",
        "hidratante",
        "conjunto",
        "gift set",
    ]

    for i, row in enumerate(rows):
        if any(w in row["name"].lower() for w in SKIP_WORDS):
            unmatched += 1
            continue

        tipo = get_tipo(row["store_slug"], row["name"], row["url"])
        index = decant_index if tipo == "decant" else frasco_index
        slug, score = find_slug(row["name"], row["brand"] or "", index, catalog)

        if slug:
            matched += 1
            ok = send_price(
                slug,
                row["store_name"],
                row["price"],
                row["url"],
                row["store_slug"],
                tipo,
            )
            if ok:
                sent += 1
            else:
                erros += 1
        else:
            unmatched += 1

        if (i + 1) % 500 == 0:
            log.info(
                f"[{i + 1}/{len(rows)}] matched={matched} sent={sent} unmatched={unmatched} erros={erros}"
            )

        time.sleep(0.05)

    log.info(
        f"=== Concluído: matched={matched} sent={sent} unmatched={unmatched} erros={erros} ==="
    )

if __name__ == "__main__":
    run()
