import logging
import re
import requests
import os
import time
from typing import Optional
from urllib.parse import quote

from database.db import get_db
DECANT_STORE_SLUGS = ["kingofDecants", "bhdecants", "macdecants", "sgimportados", "decantslondrina"]
from database.models import Product, Price, Store
from database.repository import PriceRepository

logger = logging.getLogger(__name__)

LOVABLE_API_URL = os.environ.get("LOVABLE_API_URL", "https://scentsearch.lovable.app")
LOVABLE_API_KEY = os.environ.get("LOVABLE_API_KEY", "")

RAKUTEN_ID = "bvmD8pUGdGc"
AFFILIATE_MIDS = {
    "opaque": "47714",
}

def make_deeplink(store_slug: str, url: str) -> str:
    mid = AFFILIATE_MIDS.get(store_slug)
    if mid:
        return f"https://click.linksynergy.com/deeplink?id={RAKUTEN_ID}&mid={mid}&murl={quote(url, safe='')}"
    return url


def _post_with_retry(url, json, headers, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            r = requests.post(url, json=json, headers=headers, timeout=30)
            return r
        except requests.exceptions.Timeout:
            if attempt < max_attempts - 1:
                time.sleep(15)
            else:
                raise
        except requests.exceptions.ConnectionError:
            if attempt < max_attempts - 1:
                time.sleep(30)
            else:
                raise


class LovableSyncService:
    def __init__(self):
        self.base_url = LOVABLE_API_URL
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LOVABLE_API_KEY}",
        }

    def is_available(self) -> bool:
        return bool(LOVABLE_API_KEY)

    def sync_product(self, product: Product, store: Store, latest_price: Optional[Price]) -> dict:
        if not self.is_available():
            return {"status": "skipped", "reason": "Lovable API não configurada"}

        if not latest_price:
            return {"status": "skipped", "reason": "Sem dados de preço"}

        slug = self._generate_slug(product.name)

        perfume_payload = {
            "nome": product.name,
            "marca": product.brand or "Sem marca",
            "imagem_url": product.image_url or "https://placehold.co/400x400?text=Perfume",
            "slug": slug,
            "tipo": "decant" if store.slug in DECANT_STORE_SLUGS else "perfume",
        }

        try:
            r = _post_with_retry(f"{self.base_url}/api/ingest/perfumes", perfume_payload, self.headers)
        except Exception as e:
            logger.error(f"Timeout/erro ao enviar perfume {product.name}: {e}")
            return {"status": "error", "reason": "Timeout perfume"}

        if r.status_code not in (200, 201):
            logger.error(f"Erro ao enviar perfume {product.name}: {r.status_code} {r.text}")
            return {"status": "error", "reason": f"Perfume: {r.status_code}"}

        preco_payload = {
            "perfume_slug": slug,
            "loja": store.name,
            "preco": float(latest_price.price),
            "link_afiliado": make_deeplink(store.slug, product.url),
            "disponivel": True,
        }

        try:
            r = _post_with_retry(f"{self.base_url}/api/ingest/precos", preco_payload, self.headers)
        except Exception as e:
            logger.error(f"Timeout/erro ao enviar preço {product.name}: {e}")
            return {"status": "error", "reason": "Timeout preço"}

        if r.status_code not in (200, 201):
            logger.error(f"Erro ao enviar preço {product.name}: {r.status_code} {r.text}")
            return {"status": "error", "reason": f"Preço: {r.status_code}"}

        return {"status": "synced"}

    def sync_all_products(self, limit: int = 500) -> dict:
        if not self.is_available():
            logger.warning("Lovable sync ignorado: API key não configurada")
            return {"synced": 0, "errors": 0, "skipped": "not_configured"}

        synced = 0
        errors = 0

        with get_db() as db:
            from sqlalchemy.orm import joinedload
            products = (
                db.query(Product)
                .options(joinedload(Product.store))
                .join(Price)
                .filter(Product.store.has())
                .limit(limit)
                .all()
            )

            for i, product in enumerate(products):
                try:
                    price_repo = PriceRepository(db)
                    latest_price = price_repo.get_latest(product.id)
                    result = self.sync_product(product, product.store, latest_price)

                    if result["status"] == "synced":
                        synced += 1
                    elif result["status"] == "error":
                        errors += 1
                except Exception as e:
                    logger.error(f"Erro ao sincronizar {product.name}: {e}")
                    errors += 1

                time.sleep(0.1)

        logger.info(f"Lovable sync completo: {synced} sincronizados, {errors} erros")
        return {"synced": synced, "errors": errors}

    def _generate_slug(self, name: str) -> str:
        slug = name.lower()
        slug = re.sub(r'[áàãâä]', 'a', slug)
        slug = re.sub(r'[éèêë]', 'e', slug)
        slug = re.sub(r'[íìîï]', 'i', slug)
        slug = re.sub(r'[óòõôö]', 'o', slug)
        slug = re.sub(r'[úùûü]', 'u', slug)
        slug = re.sub(r'[ç]', 'c', slug)
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        return slug.strip('-')

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler("/tmp/sync3.log"), logging.StreamHandler()])
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    service = LovableSyncService()
    print(f"API disponível: {service.is_available()}")
    result = service.sync_all_products(limit=limit or 999999)
    print(result)
