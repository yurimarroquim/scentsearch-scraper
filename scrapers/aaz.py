import requests
from urllib.parse import quote_plus
from scrapers.base import BaseScraper, PriceData, ScrapingResult
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

CATEGORIES = [
    "C:/3/",   # Perfumaria (inclui Perfumes Importados e Infantil)
]

class AAZPerfumesScraper(BaseScraper):
    store_name = "AAZ Perfumes"
    store_slug = "aaz"
    base_url = "https://www.aazperfumes.com.br"

    def scrape(self):
        products = []
        errors = []
        seen_ids = set()
        step = 50

        for category in CATEGORIES:
            from_idx = 0
            while True:
                try:
                    resp = requests.get(
                        f"{self.base_url}/api/catalog_system/pub/products/search",
                        headers=HEADERS,
                        params={"fq": category, "_from": from_idx, "_to": from_idx + step - 1},
                        timeout=(5, 30)
                    )
                    if resp.status_code not in (200, 206):
                        errors.append(f"cat {category} p{from_idx}: HTTP {resp.status_code}")
                        break

                    items = resp.json()
                    if not items:
                        break

                    for item in items:
                        try:
                            pid = item.get("productId")
                            if pid in seen_ids:
                                continue
                            seen_ids.add(pid)

                            name = item.get("productName", "").strip()
                            if not name:
                                continue

                            brand = item.get("brand") or None
                            link_text = item.get("linkText", "")
                            product_url = f"{self.base_url}/{link_text}/p"

                            variants = item.get("items", [])
                            if not variants:
                                continue
                            variant = variants[0]
                            sellers = variant.get("sellers", [])
                            if not sellers:
                                continue
                            offer = sellers[0].get("commertialOffer", {})
                            price = offer.get("Price")
                            available = offer.get("IsAvailable", False)
                            if not price or not available:
                                continue

                            images = variant.get("images", [])
                            image_url = (
                                images[0].get("imageUrl", "https://placehold.co/400x400?text=Perfume")
                                if images else "https://placehold.co/400x400?text=Perfume"
                            )

                            products.append(PriceData(
                                name=name,
                                brand=brand,
                                price=float(price),
                                url=product_url,
                                image_url=image_url,
                                in_stock=True,
                                category="perfumes"
                            ))
                        except Exception as e:
                            errors.append(str(e))

                    logger.info(f"[AAZ] cat {category} p{from_idx}: {len(items)} itens")

                    if len(items) < step:
                        break
                    from_idx += step

                except Exception as e:
                    errors.append(f"cat {category} p{from_idx}: {e}")
                    break

        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors)
        )
