import logging
import requests
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)


class SienoPerfumariaScraper(BaseScraper):
    store_name = "Sieno Perfumaria"
    store_slug = "sieno"
    base_url = "https://www.sieno.com.br"

    COLLECTIONS = [
        "perfumes-femininos-1",
        "perfumes-masculinos-antigo",
        "lp-perfumes-importados-em-oferta",
    ]

    def scrape(self) -> ScrapingResult:
        for collection in self.COLLECTIONS:
            page = 1
            while True:
                url = f"{self.base_url}/collections/{collection}/products.json?limit=250&page={page}"
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code != 200:
                        break
                    data = response.json()
                    products = data.get("products", [])
                    if not products:
                        break
                    for product in products:
                        try:
                            self._parse_product(product)
                        except Exception as e:
                            logger.warning(f"Error parsing product: {e}")
                            self.result.errors += 1
                    page += 1
                    self.delay()
                except Exception as e:
                    logger.error(f"Error fetching {url}: {e}")
                    break

        return self.result

    def _parse_product(self, product: dict):
        name = product.get("title", "")
        if not name:
            return

        handle = product.get("handle", "")
        url = f"{self.base_url}/products/{handle}"

        variants = product.get("variants", [])
        if not variants:
            return

        variant = variants[0]
        price = float(variant.get("price", 0))
        if not price:
            return

        compare_price = variant.get("compare_at_price")
        original_price = float(compare_price) if compare_price else None

        images = product.get("images", [])
        image_url = images[0].get("src") if images else None

        discount = None
        if original_price and original_price > price:
            discount = round((1 - price / original_price) * 100, 1)

        volume = self.parse_volume(name)

        self.result.products.append(PriceData(
            name=name,
            url=url,
            price=price,
            volume_ml=volume,
            original_price=original_price,
            discount_percent=discount,
            image_url=image_url,
            category=self.category,
        ))
