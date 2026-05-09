import re
from scrapers.base import BaseScraper, PriceData, ScrapingResult
import logging

logger = logging.getLogger(__name__)

CATEGORY_URLS = [
    "https://www.thekingofparfums.com.br/br/produtos/",
]


class KingOfParfumsScraper(BaseScraper):
    store_name = "The King of Parfums"
    store_slug = "kingofparfums"
    base_url = "https://www.thekingofparfums.com.br"

    def parse_price(self, text):
        text = text.strip().replace("R$", "").replace(".", "").replace(",", ".").strip()
        try:
            return float(text)
        except Exception:
            return None

    def scrape(self):
        products = []
        errors = []
        seen_ids = set()

        for cat_url in CATEGORY_URLS:
            page = 1
            while True:
                url = cat_url if page == 1 else f"{cat_url}?page={page}"
                soup = self.get_page(url)
                if not soup:
                    break

                items = soup.select(".js-item-product")
                if not items:
                    break

                new_count = 0
                for item in items:
                    try:
                        pid = item.get("data-product-id")
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)

                        name_el = item.select_one(".js-item-name")
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        if not name:
                            continue

                        brand = None
                        if " - " in name:
                            brand = name.split(" - ")[0].strip()

                        link = item.select_one("a[href]")
                        if not link:
                            continue
                        product_url = link["href"]
                        if not product_url.startswith("http"):
                            product_url = self.base_url + product_url

                        price_el = (
                            item.select_one(".js-price-display")
                            or item.select_one(".item-price")
                        )
                        if not price_el:
                            continue
                        price = self.parse_price(price_el.get_text(strip=True))
                        if not price or price <= 0:
                            continue

                        img = item.select_one("img")
                        image_url = "https://placehold.co/400x400?text=Perfume"
                        if img:
                            src = (
                                img.get("data-srcset")
                                or img.get("data-src")
                                or img.get("src", "")
                            )
                            if src and not src.startswith("data:"):
                                if src.startswith("//"):
                                    src = "https:" + src
                                image_url = src.split(" ")[0]

                        tipo = (
                            "decant"
                            if "decant" in product_url.lower() or "decant" in name.lower()
                            else "perfume"
                        )

                        products.append(
                            PriceData(
                                name=name,
                                brand=brand,
                                price=price,
                                url=product_url,
                                image_url=image_url,
                                in_stock=True,
                                category="perfume",
                                tipo=tipo,
                            )
                        )
                        new_count += 1
                    except Exception as e:
                        errors.append(str(e))

                logger.info(
                    f"[KingOfParfums] Página {page}: {len(items)} itens ({new_count} novos)"
                )
                if new_count == 0:
                    break
                page += 1
                self.delay()

        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors),
        )
