import json
import logging
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)

SUBCATEGORIAS = [
    "perfumes/feminino",
    "perfumes/masculino",
    "perfumes/unissex",
    "perfumes/arabian",
    "perfumes/infantil",
]


class BelezaNaWebScraper(BaseScraper):
    store_name = "Beleza na Web"
    store_slug = "belezanaweb"
    base_url = "https://www.belezanaweb.com.br"

    def scrape(self) -> ScrapingResult:
        seen_skus = set()

        for subcat in SUBCATEGORIAS:
            page = 1
            while True:
                url = f"{self.base_url}/{subcat}/?pagina={page}"
                soup = self.get_page(url)
                if not soup:
                    break

                articles = soup.select("article.showcase-item")
                if not articles:
                    break

                new_in_page = 0
                for art in articles:
                    try:
                        event = json.loads(art.get("data-event", "{}"))
                        sku = str(event.get("sku", ""))
                        if not sku or sku in seen_skus:
                            continue
                        seen_skus.add(sku)

                        name = event.get("productName", "").strip()
                        price = event.get("price")
                        brand = event.get("brand", "").replace("-", " ").title().strip()

                        if not name or not price:
                            continue

                        a = art.select_one("a[href]")
                        href = ""
                        if a:
                            href = a.get("href", "")
                            if href.startswith("/"):
                                href = self.base_url + href

                        img = art.select_one("img[src], img[data-src]")
                        image_url = (img.get("data-src") or img.get("src", "")) if img else ""

                        self.result.products.append(PriceData(
                            name=name,
                            url=href,
                            price=float(price),
                            brand=brand,
                            sku=sku,
                            image_url=image_url or None,
                            volume_ml=self.parse_volume(name),
                            category=self.category,
                        ))
                        new_in_page += 1

                    except Exception as e:
                        logger.warning(f"Error parsing product: {e}")
                        self.result.errors += 1

                logger.info(f"[BNW] {subcat} p.{page}: {new_in_page} novos")
                if new_in_page == 0:
                    break

                page += 1
                self.delay()

        return self.result
