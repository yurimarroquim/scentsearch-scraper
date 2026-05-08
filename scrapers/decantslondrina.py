import json
import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult


class DecantsLondrinaScraper(BaseScraper):
    store_name = "Decants Londrina"
    store_slug = "decantslondrina"
    base_url = "https://www.decantslondrina.com.br"

    CATEGORIES = ['/produtos/']

    def __init__(self):
        super().__init__()
        self.session.headers.update({"Accept-Encoding": "gzip, deflate"})

    def get_page(self, url, params=None):
        response = self.session.get(url, params=params, timeout=(5, 30), allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def scrape_category(self, category_path):
        products = []
        seen_urls = set()
        page = 1

        while True:
            url = f"{self.base_url}{category_path}"
            try:
                soup = self.get_page(url, params={"limit": 100, "page": page})
            except Exception as e:
                print(f"Erro na pagina {page}: {e}")
                break

            items = soup.select("div[data-product-id]")
            if not items:
                break

            new_count = 0
            for item in items:
                link = item.select_one("a.item-name, a[class*='item-name'], h2 a, .js-item-name a")
                product_url = ""
                name = ""

                if link:
                    product_url = link.get("href", "")
                    name = link.get("title") or link.get("aria-label") or link.get_text(strip=True)
                else:
                    a = item.select_one("a[href]")
                    if a:
                        product_url = a.get("href", "")
                        name = a.get("title") or a.get("aria-label") or a.get_text(strip=True)

                if not product_url or product_url in seen_urls:
                    continue
                seen_urls.add(product_url)
                new_count += 1

                if name.startswith("Perfume "):
                    name = name[8:]
                brand = name.split()[0] if name else "Sem marca"

                price = None
                image_url = "https://placehold.co/400x400?text=Perfume"
                container = item.select_one("[data-variants]")
                if container:
                    try:
                        variants = json.loads(container.get("data-variants", "[]"))
                        if variants:
                            v = variants[0]
                            price_num = v.get("price_number")
                            if price_num is not None:
                                price = float(price_num)
                            img = v.get("image_url", "")
                            if img:
                                if img.startswith("//"):
                                    img = "https:" + img
                                image_url = img
                    except (json.JSONDecodeError, ValueError):
                        pass

                products.append(PriceData(
                    name=name,
                    brand=brand or "Sem marca",
                    price=price,
                    url=product_url,
                    image_url=image_url,
                ))

            if new_count == 0:
                break
            page += 1

        return products

    def scrape(self):
        all_products = []
        for category in self.CATEGORIES:
            print(f"Scraping categoria: {category}")
            products = self.scrape_category(category)
            print(f"  {len(products)} produtos encontrados")
            all_products.extend(products)

        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=all_products,
        )
