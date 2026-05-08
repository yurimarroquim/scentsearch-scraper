import requests
import time
from scrapers.base import BaseScraper, PriceData, ScrapingResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

class NeecheScraper(BaseScraper):
    store_name = "Neeche"
    store_slug = "neeche"
    base_url = "https://www.neeche.com.br"

    def scrape(self):
        products = []
        errors = []
        step = 50
        from_idx = 0

        while True:
            try:
                resp = requests.get(
                    f"{self.base_url}/api/catalog_system/pub/products/search",
                    headers=HEADERS,
                    params={"ft": "perfume", "_from": from_idx, "_to": from_idx + step - 1},
                    timeout=(5, 30)
                )
                resp.raise_for_status()
                items = resp.json()
                if not items:
                    break
                for item in items:
                    try:
                        name = item.get("productName", "").strip()
                        if not name:
                            continue
                        brand = item.get("brand") or None
                        link_text = item.get("linkText", "")
                        product_url = f"{self.base_url}/{link_text}/p"
                        variants = item.get("items", [])
                        if not variants:
                            continue
                        variant = variants[0]
                        sellers = variant.get("sellers", [])
                        if not sellers:
                            continue
                        offer = sellers[0].get("commertialOffer", {})
                        price = offer.get("Price")
                        available = offer.get("IsAvailable", False)
                        if not price or not available:
                            continue
                        images = variant.get("images", [])
                        image_url = images[0].get("imageUrl", "https://placehold.co/400x400?text=Perfume") if images else "https://placehold.co/400x400?text=Perfume"
                        products.append(PriceData(name=name, brand=brand, price=float(price), url=product_url, image_url=image_url, in_stock=True, category="perfumes"))
                    except Exception as e:
                        errors.append(str(e))
                if len(items) < step:
                    break
                from_idx += step
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"pagina {from_idx}: {e}")
                break

        return ScrapingResult(store_slug=self.store_slug, store_name=self.store_name, products=products, errors=len(errors))
