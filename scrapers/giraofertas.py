import json
import logging
import re

from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)

CATEGORY_URLS = [
    "https://www.giraofertas.com.br/categoria/perfumes/",
    "https://www.giraofertas.com.br/categoria/decants/",
]


class GiraoFertasScraper(BaseScraper):
    store_name = "GiraoFertas"
    store_slug = "giraofertas"
    base_url = "https://www.giraofertas.com.br"

    def _extract_products(self, soup):
        products = []
        items = (
            soup.select("ul.products li.product")
            or soup.select("li.product")
            or soup.select(".product-type-simple")
        )
        for item in items:
            try:
                link_el = item.find("a", class_=re.compile(r"woocommerce-LoopProduct-link|product-link"))
                if not link_el:
                    link_el = item.find("a", href=re.compile(r"/produto/|/product/"))
                if not link_el:
                    link_el = item.find("a")
                url = link_el.get("href", "") if link_el else ""

                name_el = (
                    item.find("h2", class_=re.compile(r"woocommerce-loop-product__title|product-title"))
                    or item.find("h2")
                    or item.find("h3")
                )
                name = name_el.get_text(strip=True) if name_el else ""

                # Brand + price via GTM data layer (WooCommerce)
                brand = None
                price = None
                gtm = item.find("span", class_="gtm4wp_productdata")
                if gtm:
                    try:
                        data = json.loads(gtm.get("data-gtm4wp_product_data", "{}"))
                        brand = data.get("brand") or None
                        val = float(data.get("price", 0))
                        if val > 0:
                            price = val
                    except Exception:
                        pass

                if not price:
                    ins = item.find("ins")
                    bdi = (ins.find("bdi") if ins else None) or item.find("bdi")
                    price_str = bdi.get_text(strip=True) if bdi else ""
                    price = self.parse_price(price_str)

                img = item.find("img")
                image_url = (
                    img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                ) if img else None

                if not name or not url or not price or price <= 0:
                    continue

                products.append(PriceData(
                    name=name,
                    url=url,
                    price=price,
                    brand=brand,
                    image_url=image_url,
                    volume_ml=self.parse_volume(name),
                    in_stock=True,
                    category="perfume",
                    tipo="frasco",
                ))
            except Exception:
                continue
        return products

    def _has_next_page(self, soup):
        return bool(
            soup.find("a", class_=re.compile(r"next|next-page"))
            or soup.find("a", attrs={"rel": "next"})
        )

    def _scrape_category(self, base_cat_url):
        all_products = []
        seen_urls = set()
        page = 1
        while True:
            url = base_cat_url if page == 1 else f"{base_cat_url}page/{page}/"
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
            logger.info(f"[giraofertas] {base_cat_url} page {page}: +{len(new)}")
            if not self._has_next_page(soup):
                break
            page += 1
            self.delay()
        return all_products

    def scrape(self):
        for cat_url in CATEGORY_URLS:
            products = self._scrape_category(cat_url)
            self.result.products.extend(products)
            logger.info(f"[giraofertas] {cat_url}: {len(products)} total")
        return self.result
