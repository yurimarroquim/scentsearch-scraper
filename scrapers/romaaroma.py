import re
import json
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult


class RomaAromaScraper(BaseScraper):
    store_name = "Roma Aroma"
    store_slug = "roma-aroma"
    base_url = "https://www.romaaroma.com.br"
    CATEGORIES = [
        "/perfumes-importados/",
        "/perfumes-arabes/",
        "/perfumes-nacionais/",
    ]

    def __init__(self):
        super().__init__()
        self.session.headers.update({"Accept-Encoding": "gzip, deflate"})

    def get_page(self, url, params=None):
        response = self.session.get(url, params=params, timeout=(5, 30))
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def scrape(self) -> ScrapingResult:
        products = []
        errors = []

        for category_path in self.CATEGORIES:
            page = 1
            while True:
                url = f"{self.base_url}{category_path}"
                try:
                    soup = self.get_page(url, params={"limit": 100, "page": page})
                    items = soup.select("div[data-product-id]")
                    if not items:
                        break

                    print(f"  {len(items)} produtos | {category_path} p{page}")

                    for item in items:
                        try:
                            link_el = (
                                item.select_one("a.item-name")
                                or item.select_one("a[href*='/produtos/']")
                            )
                            if not link_el:
                                continue
                            name = link_el.get("title", "").strip() or link_el.get_text(strip=True)
                            if not name:
                                continue
                            product_url = link_el.get("href", "")

                            if product_url and not product_url.startswith("http"):
                                product_url = self.base_url + product_url

                            # Preço via data-variants JSON
                            variants_raw = item.get("data-variants", "[]")
                            variants = json.loads(variants_raw)
                            price = None
                            image_url = None
                            if variants:
                                price_raw = variants[0].get("price_number")
                                price = float(price_raw) / 100 if price_raw else None
                                image_url = variants[0].get("image_url", "")

                            # Fallback de preço via HTML
                            if price is None:
                                price_tag = item.select_one(".js-price-display, .price")
                                if price_tag:
                                    txt = re.sub(r"[^\d,]", "", price_tag.get_text()).replace(",", ".")
                                    price = float(txt) if txt else None

                            if price is None or price <= 0:
                                continue

                            products.append(PriceData(
                                name=name,
                                url=product_url,
                                price=price,
                                brand=None,
                                image_url=image_url or "https://placehold.co/400x400?text=Perfume",
                                in_stock=True,
                                category=category_path.strip("/"),
                            ))
                        except Exception as e:
                            errors.append(str(e))

                    if len(items) < 100:
                        break
                    page += 1

                except Exception as e:
                    errors.append(f"{category_path} p{page}: {e}")
                    break

        print(f"  Total: {len(products)} produtos")
        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors),
        )
