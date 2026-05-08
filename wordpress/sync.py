import logging
from datetime import datetime
from typing import Optional

from wordpress.client import WordPressClient
from database.db import get_db
from database.models import Product, Price, Store, WordPressSync
from database.repository import PriceRepository

logger = logging.getLogger(__name__)


class WordPressSyncService:
    def __init__(self):
        self.client = WordPressClient()

    def is_available(self) -> bool:
        return self.client.is_configured()

    def sync_product(self, product: Product, store: Store, latest_price: Optional[Price]) -> dict:
        if not self.is_available():
            return {"status": "skipped", "reason": "WordPress not configured"}

        if not latest_price:
            return {"status": "skipped", "reason": "No price data"}

        title = f"{product.name}"
        content = self._build_product_content(product, store, latest_price)

        with get_db() as db:
            existing_sync = db.query(WordPressSync).filter(
                WordPressSync.product_id == product.id
            ).first()

        if existing_sync and existing_sync.wp_post_id:
            result = self.client.update_post(
                post_id=existing_sync.wp_post_id,
                title=title,
                content=content,
                meta=self._build_meta(product, store, latest_price),
            )
            status = "updated" if result else "error"
        else:
            result = self.client.create_post(
                title=title,
                content=content,
                status="publish",
                meta=self._build_meta(product, store, latest_price),
            )
            status = "created" if result else "error"

            if result:
                with get_db() as db:
                    sync = WordPressSync(
                        product_id=product.id,
                        wp_post_id=result["id"],
                        status="synced",
                        last_synced=datetime.utcnow(),
                    )
                    db.add(sync)

        return {"status": status, "wp_post_id": result["id"] if result else None}

    def sync_all_products(self, limit: int = 100) -> dict:
        if not self.is_available():
            logger.warning("WordPress sync skipped: not configured")
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
                price_repo = PriceRepository(db)
                latest_price = price_repo.get_latest(product.id)

                result = self.sync_product(product, product.store, latest_price)
                if result["status"] in ("created", "updated"):
                    synced += 1
                elif result["status"] == "error":
                    errors += 1

        logger.info(f"WordPress sync complete: {synced} synced, {errors} errors")
        return {"synced": synced, "errors": errors}

    def _build_product_content(self, product: Product, store: Store, price: Price) -> str:
        lines = [
            f"<h2>{product.name}</h2>",
        ]

        if product.brand:
            lines.append(f"<p><strong>Marca:</strong> {product.brand}</p>")

        if product.volume_ml:
            lines.append(f"<p><strong>Volume:</strong> {product.volume_ml}ml</p>")

        lines.append(f"<p><strong>Loja:</strong> {store.name}</p>")

        price_str = f"R$ {price.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        lines.append(f"<p><strong>Preço:</strong> {price_str}</p>")

        if price.original_price and price.original_price > price.price:
            orig_str = f"R$ {price.original_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"<p><strong>Preço Original:</strong> <s>{orig_str}</s></p>")

        if price.discount_percent:
            lines.append(f"<p><strong>Desconto:</strong> {price.discount_percent:.0f}%</p>")

        lines.append(
            f'<p><a href="{product.url}" target="_blank" rel="nofollow">Ver na {store.name}</a></p>'
        )

        if product.image_url:
            lines.append(f'<img src="{product.image_url}" alt="{product.name}" />')

        lines.append(
            f"<p><small>Atualizado em: {price.scraped_at.strftime('%d/%m/%Y %H:%M')}</small></p>"
        )

        return "\n".join(lines)

    def _build_meta(self, product: Product, store: Store, price: Price) -> dict:
        return {
            "scentsearch_price": str(price.price),
            "scentsearch_store": store.name,
            "scentsearch_url": product.url,
            "scentsearch_updated": price.scraped_at.isoformat(),
        }
