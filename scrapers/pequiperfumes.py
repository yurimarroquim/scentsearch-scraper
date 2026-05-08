import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult


class PequiPerfumesScraper(BaseScraper):
    store_name = "Pequi Perfumes"
    store_slug = "pequiperfumes"
    base_url = "https://www.pequiperfumes.com.br"

    CATEGORIES = ["/perfumes1/", "/decant/"]

    def __init__(self):
        super().__init__()
        self.session.headers.update({"Accept-Encoding": "gzip, deflate"})

    def get_page(self, url, params=None):
        response = self.session.get(url, params=params, timeout=(5, 30), allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def parse_price(self, price_text):
        if not price_text:
            return None
        cleaned = re.sub(r"[^\d,]", "", price_text).replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

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
                link = item.select_one("a.item-name")
                if not link:
                    continue

                product_url = link.get("href", "")
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)
                new_count += 1

                name = link.get("title") or link.get("aria-label") or link.get_text(strip=True)
                if name.startswith("Perfume "):
                    name = name[8:]

                brand = name.split()[0] if name else "Sem marca"

                price_el = item.select_one("span.preco-produto")
                price = self.parse_price(price_el.get_text(strip=True)) if price_el else None

                img = item.select_one("img.item-image")
                image_url = ""
                if img:
                    src = img.get("src", "") or ""
                    if src.startswith("//"):
                        src = "https:" + src
                    image_url = src

                products.append(PriceData(
                    name=name,
                    brand=brand,
                    price=price,
                    url=product_url,
                    image_url=image_url or "https://placehold.co/400x400?text=Perfume",

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
