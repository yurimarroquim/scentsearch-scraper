import logging
from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)


class SephoraBrasilScraper(BaseScraper):
    store_name = "Sephora Brasil"
    store_slug = "sephora"
    base_url = "https://www.sephora.com.br"
    PAGE_SIZE = 50

    def scrape(self):
        seen_urls = set()
        offset = 0

        while True:
            url = f"{self.base_url}/api/catalog_system/pub/products/search/perfumes"
            try:
                resp = self.session.get(
                    url,
                    params={"_from": offset, "_to": offset + self.PAGE_SIZE - 1},
                    timeout=30,
                )
                resp.raise_for_status()
                items = resp.json()
            except Exception as e:
                logger.warning(f"[Sephora] API error offset={offset}: {e}")
                break

            if not items:
                break

            for item in items:
                try:
                    self._parse_vtex_product(item, seen_urls)
                except Exception as e:
                    logger.warning(f"[Sephora] parse error: {e}")
                    self.result.errors += 1

            logger.info(f"[Sephora] offset={offset}: {len(items)} produtos")

            if len(items) < self.PAGE_SIZE:
                break

            offset += self.PAGE_SIZE
            self.delay()

        return self.result

    def _parse_vtex_product(self, item, seen_urls):
        brand = item.get("brand") or None
        base_link = item.get("link", "") or ""
        if base_link and not base_link.startswith("http"):
            base_link = self.base_url + base_link

        for sku in item.get("items", []):
            name = (
                sku.get("nameComplete")
                or sku.get("name")
                or item.get("productName", "")
            ).strip()
            if not name:
                continue

            sku_id = sku.get("itemId", "")
            link = f"{base_link}?skuId={sku_id}" if base_link and sku_id else base_link
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            images = sku.get("images", [])
            image_url = images[0].get("imageUrl", "") if images else ""

            price = None
            in_stock = False
            for seller in sku.get("sellers", []):
                offer = seller.get("commertialOffer", {})
                p = offer.get("Price") or offer.get("ListPrice")
                if p and float(p) > 0:
                    price = float(p)
                    in_stock = offer.get("AvailableQuantity", 0) > 0
                    break

            if not price:
                continue

            self.result.products.append(PriceData(
                name=name,
                url=link,
                price=price,
                brand=brand,
                volume_ml=self.parse_volume(name),
                image_url=image_url or None,
                in_stock=in_stock,
                category="perfume",
            ))
