import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult


class OpaqueScraper(BaseScraper):
    store_name = "Opaque"
    store_slug = "opaque"
    base_url = "https://www.opaque.com.br"

    RAKUTEN_ID = "bvmD8pUGdGc"
    RAKUTEN_MID = "47714"
    CATEGORIES = ["/perfumes"]

    def __init__(self):
        super().__init__()
        self.session.headers.update({"Accept-Encoding": "gzip, deflate"})

    def affiliate_url(self, url):
        encoded = quote_plus(url)
        return f"https://click.linksynergy.com/deeplink?id={self.RAKUTEN_ID}&mid={self.RAKUTEN_MID}&murl={encoded}"

    def get_page(self, url, params=None):
        response = self.session.get(url, params=params, timeout=(5, 30), allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def parse_price(self, text):
        if not text:
            return None
        cleaned = re.sub(r"[^\d,]", "", text.strip()).replace(",", ".")
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
                soup = self.get_page(url, params={"PS": 50, "PageNumber": page})
            except Exception as e:
                print(f"Erro na pagina {page}: {e}")
                break

            items = soup.select("div.produto-na-prateleira")
            if not items:
                break

            new_count = 0
            for item in items:
                # URL
                link = item.select_one('a[href*="/p"]')
                if not link:
                    continue
                product_url = link.get("href", "")
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)
                new_count += 1

                # Nome e marca
                name = item.select_one("div.nome")
                name = name.get_text(strip=True) if name else item.get("title", "")
                brand_el = item.select_one("div.brand-nome")
                brand = brand_el.get_text(strip=True) if brand_el else (name.split()[0] if name else "Sem marca")

                # Preco atual
                price_el = item.select_one("div.principal span.value")
                price = self.parse_price(price_el.get_text()) if price_el else None

                # Imagem (via noscript)
                image_url = "https://placehold.co/400x400?text=Perfume"
                noscript = item.select_one("noscript")
                if noscript:
                    img_soup = BeautifulSoup(noscript.decode_contents(), "html.parser")
                    img = img_soup.select_one("img")
                    if img:
                        image_url = img.get("src", image_url)

                products.append(PriceData(
                    name=name,
                    brand=brand or "Sem marca",
                    price=price,
                    url=self.affiliate_url(product_url),
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
