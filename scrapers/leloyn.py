import requests
from scrapers.base import BaseScraper, PriceData, ScrapingResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

class LeLoynScraper(BaseScraper):
    store_name = "Le'Loyn Parfums"
    store_slug = "leloyn"
    base_url = "https://leloynparfums.com.br"

    def scrape(self) -> ScrapingResult:
        products = []
        errors = []
        page = 1

        while True:
            try:
                url = f"{self.base_url}/products.json"
                resp = requests.get(url, params={"limit": 250, "page": page}, headers=HEADERS, timeout=(5, 30))
                resp.raise_for_status()
                data = resp.json()
                items = data.get("products", [])
                if not items:
                    break

                print(f"  {len(items)} produtos na página {page}")

                for item in items:
                    try:
                        name = item.get("title", "").strip()
                        if not name:
                            continue

                        brand = item.get("vendor", None)
                        handle = item.get("handle", "")
                        product_url = f"{self.base_url}/products/{handle}"

                        images = item.get("images", [])
                        image_url = images[0]["src"] if images else "https://placehold.co/400x400?text=Perfume"

                        variants = item.get("variants", [])
                        for variant in variants:
                            if not variant.get("available", True):
                                continue

                            price_raw = variant.get("price")
                            if not price_raw:
                                continue
                            price = float(price_raw)
                            if price <= 0:
                                continue

                            variant_title = variant.get("title", "")
                            full_name = f"{name} {variant_title}".strip() if variant_title != "Default Title" else name

                            variant_image = variant.get("featured_image")
                            if variant_image and variant_image.get("src"):
                                image_url = variant_image["src"]

                            products.append(PriceData(
                                name=full_name,
                                url=product_url,
                                price=price,
                                brand=brand,
                                image_url=image_url,
                                in_stock=True,
                                category="perfumes",
                            ))
                    except Exception as e:
                        errors.append(str(e))

                if len(items) < 250:
                    break
                page += 1

            except Exception as e:
                errors.append(f"página {page}: {e}")
                break

        print(f"  Total: {len(products)} produtos | {len(errors)} erros")
        return ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
            products=products,
            errors=len(errors),
        )
