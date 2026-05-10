import logging
import re

import requests

from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)

CATALOG_API = "https://edom-catalog.vercel.app/api/catalog"
STORE_WHATSAPP = "https://wa.me/5562982477925"


def _parse_brl(price_str: str) -> float | None:
    if not price_str:
        return None
    try:
        cleaned = re.sub(r"[^\d,]", "", price_str)
        return float(cleaned.replace(",", ".")) if cleaned else None
    except ValueError:
        return None


class EdomDecantsScraper(BaseScraper):
    store_name = "Edom Decants"
    store_slug = "edomdecants"
    base_url = STORE_WHATSAPP

    def scrape(self):
        try:
            r = requests.get(CATALOG_API, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.error(f"[edomdecants] Erro ao buscar catálogo: {e}")
            return self.result

        for item in data.get("perfumes", []):
            nome = item.get("nome", "").strip()
            if not nome:
                continue

            in_stock = "(sem estoque)" not in nome.lower()
            clean_name = re.sub(r"\s*\(sem estoque\)", "", nome, flags=re.IGNORECASE).strip()

            marca = item.get("marca", "").strip()
            display_name = f"{clean_name} - {marca}" if marca else clean_name

            price = _parse_brl(item.get("ml5", ""))
            if not price or price <= 0:
                continue

            self.result.products.append(PriceData(
                name=display_name,
                url=STORE_WHATSAPP,
                price=price,
                image_url=None,
                volume_ml=5,
                in_stock=in_stock,
                category="perfume",
                tipo="decant",
            ))

        logger.info(f"[edomdecants] {len(self.result.products)} produtos carregados")
        return self.result
