import logging
import re
from datetime import datetime
from typing import Optional

from supabase_integration.client import SupabaseClient
from database.db import get_db
from database.models import Product, Price, Store
from database.repository import PriceRepository

logger = logging.getLogger(__name__)


class SupabaseSyncService:
    def __init__(self):
        self.client = SupabaseClient()

    def is_available(self) -> bool:
        return self.client.is_configured()

    def sync_product(self, product: Product, store: Store, latest_price: Optional[Price]) -> dict:
        if not self.is_available():
            return {"status": "skipped", "reason": "Supabase not configured"}

        if not latest_price:
            return {"status": "skipped", "reason": "No price data"}

        db = self.client.get_client()
        slug = self._generate_slug(product.name)

        # Upsert perfume
        perfume_data = {
            "nome": product.name,
            "marca": product.brand or "",
            "imagem_url": product.image_url or "",
            "slug": slug,
        }

        existing = db.table("perfumes").select("id").eq("slug", slug).execute()

        if existing.data:
            perfume_id = existing.data[0]["id"]
            db.table("perfumes").update(perfume_data).eq("id", perfume_id).execute()
        else:
            result = db.table("perfumes").insert(perfume_data).execute()
            if not result.data:
                return {"status": "error", "reason": "Falha ao inserir perfume"}
            perfume_id = result.data[0]["id"]

        # Upsert preço por loja
        preco_data = {
            "perfume_id": perfume_id,
            "loja": store.name,
            "preco": float(latest_price.price),
            "link_afiliado": product.url,
            "disponivel": True,
            "atualizado_em": datetime.utcnow().isoformat(),
        }

        existing_price = (
            db.table("precos")
            .select("id")
            .eq("perfume_id", perfume_id)
            .eq("loja", store.name)
            .execute()
        )

        if existing_price.data:
            db.table("precos").update(preco_data).eq("id", existing_price.data[0]["id"]).execute()
            status = "updated"
        else:
            db.table("precos").insert(preco_data).execute()
            status = "created"

        return {"status": status}

    def sync_all_products(self, limit: int = 500) -> dict:
        if not self.is_available():
            logger.warning("Supabase sync ignorado: não configurado")
            return {"synced": 0, "errors": 0, "skipped": "not_configured"}

        synced = 0
        errors = 0

        with get_db() as db:
            from sqlalchemy.orm import joinedload
            products = (
                db.query(Product)
                .options(joinedload(Product.store))
                .limit(limit)
                .all()
            )

            for product in products:
                try:
                    price_repo = PriceRepository(db)
                    latest_price = price_repo.get_latest(product.id)
                    result = self.sync_product(product, product.store, latest_price)

                    if result["status"] in ("created", "updated"):
                        synced += 1
                    elif result["status"] == "error":
                        errors += 1
                except Exception as e:
                    logger.error(f"Erro ao sincronizar {product.name}: {e}")
                    errors += 1

        logger.info(f"Supabase sync completo: {synced} sincronizados, {errors} erros")
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
