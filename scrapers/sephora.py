import logging
from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)

CATEGORY_SLUGS = ["perfumes", "fragrancias", "fragrâncias"]


class SephoraBrasilScraper(BaseScraper):
    store_name = "Sephora Brasil"
    store_slug = "sephora"
    base_url = "https://www.sephora.com.br"
    PAGE_SIZE = 50

    def scrape(self):
        seen_urls = set()

        for slug in CATEGORY_SLUGS:
            count = self._scrape_is_category(slug, seen_urls)
            if count > 0:
                logger.info(f"[Sephora] IS/{slug} funcionou: {count} produtos")
                break
        else:
            logger.info("[Sephora] categorias IS falharam — tentando full-text")
            self._scrape_is_fulltext(seen_urls)

        return self.result

    def _scrape_is_category(self, slug, seen_urls):
        initial = len(self.result.products)
        page = 1
        while True:
            url = f"{self.base_url}/api/io/_v/api/intelligent-search/product_search/{slug}"
            try:
                resp = self.session.get(
                    url,
                    params={"locale": "pt-BR", "hideUnavailableItems": "false",
                            "priceBehavior": "LIST", "count": self.PAGE_SIZE, "page": page},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"[Sephora] IS/{slug} page={page}: {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            for prod in products:
                try:
                    self._parse_vtex_product(prod, seen_urls)
                except Exception as e:
                    logger.warning(f"[Sephora] parse error: {e}")
                    self.result.errors += 1
            logger.info(f"[Sephora] IS/{slug} page={page}: {len(products)} produtos")
            total = data.get("recordsFiltered", 0)
            if len(products) < self.PAGE_SIZE or page * self.PAGE_SIZE >= total:
                break
            page += 1
            self.delay()
        return len(self.result.products) - initial

    def _scrape_is_fulltext(self, seen_urls):
        page = 1
        while True:
            url = f"{self.base_url}/api/io/_v/api/intelligent-search/product_search"
            try:
                resp = self.session.get(
                    url,
                    params={"locale": "pt-BR", "hideUnavailableItems": "false",
                            "priceBehavior": "LIST", "count": self.PAGE_SIZE, "page": page,
                            "fullText": "perfume"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"[Sephora] IS fulltext page={page}: {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            for prod in products:
                try:
                    self._parse_vtex_product(prod, seen_urls)
                except Exception as e:
                    logger.warning(f"[Sephora] parse error: {e}")
                    self.result.errors += 1
            logger.info(f"[Sephora] IS fulltext page={page}: {len(products)} produtos")
            total = data.get("recordsFiltered", 0)
            if len(products) < self.PAGE_SIZE or page * self.PAGE_SIZE >= total:
                break
            page += 1
            self.delay()

    def _parse_vtex_product(self, item, seen_urls):
        brand = item.get("brand") or None
        base_link = item.get("link", "") or ""
        if base_link and not base_link.startswith("http"):
            base_link = self.base_url + base_link
        for sku in item.get("items", []):
            name = (sku.get("nameComplete") or sku.get("name") or item.get("productName", "")).strip()
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
                name=name, url=link, price=price, brand=brand,
                volume_ml=self.parse_volume(name), image_url=image_url or None,
                in_stock=in_stock, category="perfume",
            ))
