"""
Migração direta: SQLite local → Supabase (sem API HTTP)
Processa em lotes de 500, muito mais rápido que sync.py
"""
import os, sys, re, logging, time
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Conexão Supabase
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

DECANT_SLUGS = {"kingofDecants","bhdecants","macdecants","sgimportados","decantslondrina","neeche"}
RAKUTEN_ID = "bvmD8pUGdGc"
AFFILIATE_MIDS = {"opaque": "47714"}

def slugify(name):
    s = name.lower()
    for a, b in [("áàãâä","a"),("éèêë","e"),("íìîï","i"),("óòõôö","o"),("úùûü","u"),("ç","c")]:
        for c in a: s = s.replace(c, b)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def make_deeplink(store_slug, url):
    mid = AFFILIATE_MIDS.get(store_slug)
    if mid:
        from urllib.parse import quote
        return f"https://click.linksynergy.com/deeplink?id={RAKUTEN_ID}&mid={mid}&murl={quote(url, safe='')}"
    return url

def run():
    import sqlite3
    conn = sqlite3.connect("/home/runner/workspace/artifacts/scentsearch-scraper/data/scentsearch.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Busca todos os produtos com preço mais recente
    cur.execute("""
        SELECT p.id, p.name, p.brand, p.url, p.image_url,
               s.name as store_name, s.slug as store_slug,
               pr.price
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN prices pr ON pr.product_id = p.id
        WHERE pr.id = (
            SELECT id FROM prices WHERE product_id = p.id
            ORDER BY scraped_at DESC LIMIT 1
        )
        AND pr.in_stock = 1
        AND pr.price > 0
    """)
    rows = cur.fetchall()
    log.info(f"Total a sincronizar: {len(rows):,}")

    perfumes_ok = 0
    precos_ok = 0
    erros = 0

    for i, row in enumerate(rows):
        slug = slugify(row["name"])
        tipo = "decant" if row["store_slug"] in DECANT_SLUGS else "perfume"

        try:
            # Upsert perfume
            sb.table("perfumes").upsert({
                "nome": row["name"],
                "marca": row["brand"] or "Sem marca",
                "imagem_url": row["image_url"] or "https://placehold.co/400x400?text=Perfume",
                "slug": slug,
                "tipo": tipo,
            }, on_conflict="slug").execute()
            perfumes_ok += 1

            # Busca o id do perfume
            res = sb.table("perfumes").select("id").eq("slug", slug).single().execute()
            perfume_id = res.data["id"]

            # Upsert preço
            sb.table("precos").upsert({
                "perfume_id": perfume_id,
                "loja": row["store_name"],
                "preco": float(row["price"]),
                "link_afiliado": make_deeplink(row["store_slug"], row["url"]),
                "disponivel": True,
            }, on_conflict="perfume_id,loja").execute()
            precos_ok += 1

        except Exception as e:
            log.warning(f"Erro em '{row['name']}': {e}")
            erros += 1

        if (i+1) % 100 == 0:
            log.info(f"  [{i+1}/{len(rows)}] perfumes: {perfumes_ok} | precos: {precos_ok} | erros: {erros}")

    log.info(f"=== Concluído: {perfumes_ok} perfumes | {precos_ok} preços | {erros} erros ===")

if __name__ == "__main__":
    run()
