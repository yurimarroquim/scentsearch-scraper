import requests
import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper, PriceData, ScrapingResult
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


class KingOfParfumsScraper(BaseScraper):
    store_name = "The King of Parfums"
    store_slug = "kingofparfums"
    base_url = "https://www.thekingofparfums.com.br"

    def parse_price(self, text):
        text = text.strip().replace("R$", "").replace(".", "").replace(",", ".").strip()
        try:
            return float(text)
        except:
            return None

    def scrape(self):
        products = []
        errors = []
        seen_ids = set()
        page = 1

        while True:
            try:
                url = f"{self.base_url}/br/produtos/page/{page}/"
                resp = requests.get(url, headers=HEADERS, timeout=(5, 30))

                if resp.status_code == 404:
                    break
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".js-item-product")

                if not items:
                    break

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

                        price_el = item.select_one(".js-price-display")
                        if not price_el:
                            price_el = item.select_one(".item-price")
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
                            if "decant" in product_url.lower()
                            or "decant" in name.lower()
                            else "frasco"
                        )

                        products.append(
                            PriceData(
                                name=name,
                                brand=brand,
                                price=price,
                                url=product_url,
                                image_url=image_url,
                                in_stock=True,
                                category="perfumes",
                                tipo=tipo,
                            )
                        )
                    except Exception as e:
                        errors.append(str(e))

                logger.info(f"[KingOfParfums] Página {page}: {len(items)} itens")
                page += 1

            except Exception as e:
                errors.append(f"página {page}: {e}")
                break

        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors),
        )
