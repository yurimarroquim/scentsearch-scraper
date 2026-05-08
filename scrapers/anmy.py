import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult


class AnmyScraper(BaseScraper):
    store_name = "AnMY Perfumes"
    store_slug = "anmy"
    base_url = "https://www.anmyperfumes.com.br"
    CATEGORIES = ["/masculino", "/feminino", "/arabian", "/tester", "/perfume-unissex"]

    def scrape(self) -> ScrapingResult:
        products = []
        errors = []
        seen_urls = set()

        for category_path in self.CATEGORIES:
            page = 1
            first_page_urls = None

            while True:
                url = f"{self.base_url}{category_path}"
                try:
                    soup = self.get_page(url, params={"page": page})
                    items = soup.select("li.span3")
                    if not items:
                        break

                    page_urls = {
                        item.select_one("a.nome-produto").get("href", "")
                        for item in items
                        if item.select_one("a.nome-produto")
                    }
                    if page == 1:
                        first_page_urls = page_urls
                    elif page_urls == first_page_urls:
                        break

                    print(f"  {len(items)} produtos | {category_path} p{page}")

                    for item in items:
                        try:
                            a = item.select_one("a.nome-produto")
                            if not a:
                                continue
                            name = a.get_text(strip=True)
                            if not name:
                                continue
                            product_url = a.get("href", "")
                            if product_url and not product_url.startswith("http"):
                                product_url = self.base_url + product_url

                            if product_url in seen_urls:
                                continue
                            seen_urls.add(product_url)

                            brand = None
                            if " - " in name:
                                parts = name.rsplit(" - ", 1)
                                brand = re.sub(r"\(.*\)", "", parts[-1]).strip()
                                name = parts[0].strip()

                            price_tag = item.select_one("[data-sell-price]")
                            if price_tag:
                                price = float(price_tag.get("data-sell-price", 0))
                            else:
                                pt = item.select_one("strong.preco-promocional") or \
                                     item.select_one("strong.preco-normal")
                                if not pt:
                                    continue
                                price_clean = re.sub(r"[^\d,]", "", pt.get_text()).replace(",", ".")
                                price = float(price_clean) if price_clean else None

                            if not price or price <= 0:
                                continue

                            img = item.select_one("img.imagem-principal")
                            image_url = ""
                            if img:
                                image_url = img.get("data-imagem-caminho") or img.get("src") or ""

                            products.append(PriceData(
                                name=name,
                                url=product_url,
                                price=price,
                                brand=brand,
                                image_url=image_url or "https://placehold.co/400x400?text=Perfume",
                                in_stock=True,
                                category=category_path.strip("/"),
                            ))
                        except Exception as e:
                            errors.append(str(e))

                    page += 1

                except Exception as e:
                    errors.append(f"{category_path} p{page}: {e}")
                    break

        print(f"  Total AnMY: {len(products)} produtos")
        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors),
        )
