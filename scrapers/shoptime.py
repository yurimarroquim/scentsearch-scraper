import logging
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)


class ShoptimeScraper(BaseScraper):
    store_name = "Shoptime"
    store_slug = "shoptime"
    base_url = "https://www.shoptime.com.br"

    SEARCH_URLS = [
        f"{base_url}/busca/perfume?ordenacao=menorpreco&qtdPorPagina=48",
        f"{base_url}/busca/perfume+feminino?ordenacao=menorpreco&qtdPorPagina=48",
        f"{base_url}/busca/perfume+masculino?ordenacao=menorpreco&qtdPorPagina=48",
    ]

    def scrape(self) -> ScrapingResult:
        for url in self.SEARCH_URLS:
            soup = self.get_page(url)
            if not soup:
                continue

            products = soup.select(
                "[class*='product-card'], "
                "[class*='ProductCard'], "
                ".product-item, "
                "li[class*='product']"
            )

            for product in products:
                try:
                    self._parse_product(product)
                except Exception as e:
                    logger.warning(f"Error parsing product: {e}")
                    self.result.errors += 1

            self.delay()

        return self.result

    def _parse_product(self, element):
        name_el = element.select_one(
            "[class*='product-name'], [class*='ProductName'], "
            "h2, h3, [class*='name']"
        )
        if not name_el:
            return

        name = name_el.get_text(strip=True)
        if not name:
            return

        link_el = element.select_one("a[href]")
        if not link_el:
            return

        href = link_el.get("href", "")
        if not href.startswith("http"):
            href = self.base_url + href

        price_el = element.select_one(
            "[class*='best-price'], [class*='sale-price'], "
            "[class*='price'], span[class*='Price']"
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = self.parse_price(price_text)
        if not price:
            return

        original_el = element.select_one("[class*='list-price'], [class*='original']")
        original_price = self.parse_price(
            original_el.get_text(strip=True)
        ) if original_el else None

        image_el = element.select_one("img[src]")
        image_url = image_el.get("src") if image_el else None

        discount = None
        if original_price and original_price > price:
            discount = round((1 - price / original_price) * 100, 1)

        volume = self.parse_volume(name)

        self.result.products.append(PriceData(
            name=name,
            url=href,
            price=price,
            volume_ml=volume,
            original_price=original_price,
            discount_percent=discount,
            image_url=image_url,
            category=self.category,
        ))
