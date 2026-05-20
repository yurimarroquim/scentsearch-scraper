import logging
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)


class SephoraBrasilScraper(BaseScraper):
    store_name = "Sephora Brasil"
    store_slug = "sephora"
    base_url = "https://www.sephora.com.br"

    SEARCH_URLS = [
        f"{base_url}/perfumes",
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
                "[data-testid='product-card']"
            )

            if not products:
                products = soup.select("li[class*='product'], article[class*='product']")

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
            "[class*='product-display-name'], [class*='display-name'], "
            "[class*='product-name'], h3, h2"
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
            "[class*='formatted-price'], "
            "[class*='product-price'], "
            "[class*='price']"
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = self.parse_price(price_text)
        if not price:
            return

        brand_el = element.select_one(
            "[class*='brand-name'], [class*='product-brand'], "
            "[class*='brand']"
        )
        brand = brand_el.get_text(strip=True) if brand_el else None

        image_el = element.select_one("img[src]")
        image_url = image_el.get("src") if image_el else None

        volume = self.parse_volume(name)

        self.result.products.append(PriceData(
            name=name,
            url=href,
            price=price,
            brand=brand,
            volume_ml=volume,
            image_url=image_url,
            category=self.category,
        ))
