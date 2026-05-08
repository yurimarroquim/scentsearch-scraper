import json
import logging
import re

from scrapers.base import BaseScraper, PriceData, ScrapingResult

logger = logging.getLogger(__name__)

CATEGORIES = [
    "https://guidodecants.com.br/perfumes-masculinos/",
    "https://guidodecants.com.br/perfumes-femininos/",
]


class GuidoDecantsScraper(BaseScraper):
    store_name = "Guido Decants"
    store_slug = "guidodecants"
    base_url = "https://guidodecants.com.br"

    def _parse_product_jsonld(self, data):
        if not isinstance(data, dict) or data.get("@type") != "Product":
            return None
        name = data.get("name", "").strip()
        url = data.get("url", "")
        image = data.get("image", "")
        if isinstance(image, list):
            image = image[0] if image else ""
        offers = data.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            price = float(str(offers.get("price", "0")).replace(",", "."))
        except (ValueError, TypeError):
            return None
        if not name or not url or price <= 0:
            return None
        availability = offers.get("availability", "")
        in_stock = "OutOfStock" not in availability
        return PriceData(
            name=name,
            url=url,
            price=price,
            image_url=image or None,
            volume_ml=self.parse_volume(name),
            in_stock=in_stock,
            category="perfume",
            tipo="decant",
        )

    def _extract_products(self, soup):
        products = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, list):
                for item in data:
                    p = self._parse_product_jsonld(item)
                    if p:
                        products.append(p)
            elif data.get("@type") == "Product":
                p = self._parse_product_jsonld(data)
                if p:
                    products.append(p)
            elif data.get("@type") == "ItemList":
                for element in data.get("itemListElement", []):
                    item = element.get("item", element)
                    p = self._parse_product_jsonld(item)
                    if p:
                        products.append(p)
        if not products:
            products = self._extract_html(soup)
        return products

    def _extract_html(self, soup):
        products = []
        items = (
            soup.select("li.item")
            or soup.select(".js-item-product")
            or soup.select("article.product-card")
        )
        for item in items:
            try:
                link = item.find("a", href=re.compile(r"/produtos/"))
                if not link:
                    continue
                url = link.get("href", "")
                if url and not url.startswith("http"):
                    url = self.base_url + url
                name_el = (
                    item.find(class_=re.compile(r"item-name|product-name"))
                    or item.find("h2")
                    or item.find("h3")
                )
                name = name_el.get_text(strip=True) if name_el else ""
                price_el = item.find(class_=re.compile(r"price")) or item.find(
                    attrs={"itemprop": "price"}
                )
                price_str = price_el.get_text(strip=True) if price_el else ""
                price = self.parse_price(price_str)
                img = item.find("img")
                image_url = (img.get("src") or img.get("data-src")) if img else None
                if not name or not price or price <= 0:
                    continue
                products.append(
                    PriceData(
                        name=name,
                        url=url,
                        price=price,
                        image_url=image_url,
                        volume_ml=self.parse_volume(name),
                        in_stock=True,
                        category="perfume",
                        tipo="decant",
                    )
                )
            except Exception:
                continue
        return products

    def _scrape_category(self, base_cat_url):
        all_products = []
        seen_urls = set()
        page = 1
        while True:
            url = base_cat_url if page == 1 else f"{base_cat_url}?page={page}"
            soup = self.get_page(url)
            if not soup:
                break
            products = self._extract_products(soup)
            if not products:
                break
            new = [p for p in products if p.url not in seen_urls]
            if not new:
                break
            for p in new:
                seen_urls.add(p.url)
            all_products.extend(new)
            logger.info(f"[guidodecants] {base_cat_url} page {page}: +{len(new)}")
            page += 1
            self.delay()
        return all_products

    def scrape(self):
        for cat_url in CATEGORIES:
            products = self._scrape_category(cat_url)
            self.result.products.extend(products)
            logger.info(f"[guidodecants] {cat_url}: {len(products)} total")
        return self.result
