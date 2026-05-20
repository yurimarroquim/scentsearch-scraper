import json
import logging
import os
import re

from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)

PERFUME_RE = re.compile(r"eau|perfum|parfum|edt|edp|edc|colonia|cologne|fragran", re.I)
SITEMAP_URL = "https://www.sephora.com.br/sitemap_0-product.xml"


class SephoraBrasilScraper(BaseScraper):
    store_name = "Sephora Brasil"
    store_slug = "sephora"
    base_url = "https://www.sephora.com.br"

    def scrape(self):
        if os.environ.get("GITHUB_ACTIONS"):
            logger.info("[Sephora] GitHub Actions detectado — requer IP local, pulando")
            return self.result

        urls = self._get_perfume_urls()
        logger.info(f"[Sephora] {len(urls)} URLs encontradas no sitemap")

        for i, url in enumerate(urls, 1):
            try:
                product = self._scrape_product_page(url)
                if product:
                    self.result.products.append(product)
            except Exception as e:
                logger.warning(f"[Sephora] erro em {url}: {e}")
                self.result.errors += 1
            if i % 100 == 0:
                logger.info(f"[Sephora] {i}/{len(urls)} — {len(self.result.products)} produtos")
            self.delay()

        return self.result

    def _get_perfume_urls(self):
        try:
            resp = self.session.get(SITEMAP_URL, timeout=30)
            resp.raise_for_status()
            all_urls = re.findall(r"<loc>(https://www\.sephora\.com\.br/[^<]+)</loc>", resp.text)
            return [u for u in all_urls if PERFUME_RE.search(u)]
        except Exception as e:
            logger.warning(f"[Sephora] sitemap error: {e}")
            return []

    def _scrape_product_page(self, url):
        resp = self.session.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        html = resp.text

        # Nome, marca, imagem via JSON-LD
        name = brand = image_url = None
        m = re.search(r'ld\+json">\s*(\{.*?"@type"\s*:\s*"Product".*?\})\s*</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                name = data.get("name", "").strip()
                b = data.get("brand")
                brand = (b.get("name") if isinstance(b, dict) else b) or None
                image_url = data.get("image") or None
            except Exception:
                pass

        if not name:
            return None

        # Preço via itemprop
        pm = re.search(r'itemprop="price"\s+content="([\d.]+)"', html) or \
             re.search(r'content="([\d.]+)"\s+itemprop="price"', html)
        if not pm:
            return None
        try:
            price = float(pm.group(1))
            if price <= 0:
                return None
        except ValueError:
            return None

        # Disponibilidade
        am = re.search(r'itemprop="availability"[^>]+content="([^"]+)"', html)
        in_stock = "OutOfStock" not in (am.group(1) if am else "")

        return PriceData(
            name=name,
            url=url,
            price=price,
            brand=brand,
            volume_ml=self.parse_volume(name),
            image_url=image_url,
            in_stock=in_stock,
            category="perfume",
        )
