import logging
import re
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)

PAGE_SIZE = 48


class EpocaCosmeticosScraper(BaseScraper):
    store_name = "Época Cosméticos"
    store_slug = "epoca"
    base_url = "https://www.epocacosmeticos.com.br"

    SEARCH_TERMS = ["perfume masculino", "perfume feminino", "perfume unissex"]
    MAX_PAGES = 3

    def scrape(self) -> ScrapingResult:
        seen_urls = set()

        for term in self.SEARCH_TERMS:
            for page in range(self.MAX_PAGES):
                from_ = page * PAGE_SIZE
                to_ = from_ + PAGE_SIZE - 1
                url = (
                    f"{self.base_url}/api/catalog_system/pub/products/search"
                    f"?ft={term.replace(' ', '+')}&_from={from_}&_to={to_}"
                )

                data = self._get_json(url)
                if not data:
                    break

                count = 0
                for product in data:
                    try:
                        parsed = self._parse_vtex_product(product)
                        if parsed and parsed.url not in seen_urls:
                            seen_urls.add(parsed.url)
                            self.result.products.append(parsed)
                            count += 1
                    except Exception as e:
                        logger.warning(f"Error parsing product: {e}")
                        self.result.errors += 1

                logger.info(f"[{self.store_name}] '{term}' p.{page+1}: {count} novos produtos")

                if len(data) < PAGE_SIZE:
                    break

                self.delay()

        return self.result

    def _get_json(self, url: str):
        for attempt in range(3):
            import time, requests
            try:
                r = self.session.get(url, timeout=15, allow_redirects=True)
                if r.status_code in (200, 206):
                    ct = r.headers.get("content-type", "")
                    if "json" in ct:
                        return r.json()
                    logger.warning(f"Unexpected content-type: {ct} for {url}")
                    return None
                elif r.status_code == 429:
                    time.sleep((attempt + 1) * 10)
                else:
                    logger.warning(f"HTTP {r.status_code} for {url}")
                    return None
            except Exception as e:
                logger.warning(f"Request error ({attempt+1}/3): {e}")
                time.sleep(3)
        self.result.errors += 1
        return None

    def _parse_vtex_product(self, data: dict) -> PriceData | None:
        name = data.get("productName", "").strip()
        if not name:
            return None

        link = data.get("link", "")
        if not link:
            return None
        if link.startswith("http") and "vtexcommercestable" in link:
            link_text = data.get("linkText", "")
            link = f"{self.base_url}/{link_text}/p" if link_text else link

        brand = data.get("brand", "").strip() or None

        items = data.get("items") or []
        item = items[0] if items else {}

        item_name = item.get("name", "")
        volume_ml = self.parse_volume(item_name) or self.parse_volume(name)

        images = item.get("images") or []
        image_url = images[0].get("imageUrl") if images else None

        sellers = item.get("sellers") or []
        seller = sellers[0] if sellers else {}
        offer = seller.get("commertialOffer", {})

        price = offer.get("Price")
        if not price or price == 0:
            return None

        list_price = offer.get("ListPrice")
        original_price = list_price if list_price and list_price > price else None

        discount = None
        if original_price:
            discount = round((1 - price / original_price) * 100, 1)

        available_qty = offer.get("AvailableQuantity", 0)
        in_stock = available_qty > 0

        return PriceData(
            name=name,
            url=link,
            price=price,
            brand=brand,
            volume_ml=volume_ml,
            original_price=original_price,
            discount_percent=discount,
            image_url=image_url,
            in_stock=in_stock,
            category=self.category,
        )
