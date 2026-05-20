import logging
from scrapers.base import BaseScraper, PriceData

logger = logging.getLogger(__name__)

PERFUME_KEYWORDS = ["perfume", "fragr", "eau de", "colônia", "cologne", "parfum"]


class SephoraBrasilScraper(BaseScraper):
    store_name = "Sephora Brasil"
    store_slug = "sephora"
    base_url = "https://www.sephora.com.br"
    PAGE_SIZE = 50

    def scrape(self):
        seen_urls = set()

        category_ids = self._get_perfume_category_ids()
        if category_ids:
            logger.info(f"[Sephora] encontrou {len(category_ids)} categorias de perfume: {category_ids}")
            for cat_id in category_ids:
                self._scrape_by_fq(f"C:/{cat_id}/", seen_urls)
        else:
            logger.info("[Sephora] árvore de categorias falhou — usando busca full-text")
            self._scrape_by_fq("H:1", seen_urls, fallback_ft="perfume")

        return self.result

    # ---------- category tree discovery ----------

    def _get_perfume_category_ids(self):
        try:
            resp = self.session.get(
                f"{self.base_url}/api/catalog_system/pub/category/tree/3",
                timeout=30,
            )
            resp.raise_for_status()
            tree = resp.json()
            ids = []
            self._collect_perfume_ids(tree, ids)
            return ids
        except Exception as e:
            logger.warning(f"[Sephora] category tree error: {e}")
            return []

    def _collect_perfume_ids(self, nodes, ids):
        for node in nodes:
            name_lower = node.get("name", "").lower()
            if any(k in name_lower for k in PERFUME_KEYWORDS):
                ids.append(node["id"])
            self._collect_perfume_ids(node.get("children", []), ids)

    # ---------- paginated catalog search ----------

    def _scrape_by_fq(self, fq_value, seen_urls, fallback_ft=None):
        offset = 0
        while True:
            params = {"fq": fq_value, "_from": offset, "_to": offset + self.PAGE_SIZE - 1}
            if fallback_ft:
                params["ft"] = fallback_ft
            url = f"{self.base_url}/api/catalog_system/pub/products/search/"
            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                items = resp.json()
            except Exception as e:
                logger.warning(f"[Sephora] API error fq={fq_value} offset={offset}: {e}")
                break
            if not items:
                break
            for item in items:
                try:
                    self._parse_vtex_product(item, seen_urls)
                except Exception as e:
                    logger.warning(f"[Sephora] parse error: {e}")
                    self.result.errors += 1
            logger.info(f"[Sephora] fq={fq_value} offset={offset}: {len(items)} produtos")
            if len(items) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
            self.delay()

    # ---------- product parser ----------

    def _parse_vtex_product(self, item, seen_urls):
        brand = item.get("brand") or None
        base_link = item.get("link", "") or ""
        if base_link and not base_link.startswith("http"):
            base_link = self.base_url + base_link

        for sku in item.get("items", []):
            name = (
                sku.get("nameComplete")
                or sku.get("name")
                or item.get("productName", "")
            ).strip()
            if not name:
                continue
            sku_id = sku.get("itemId", "")
            link = f"{base_link}?skuId={sku_id}" if base_link and sku_id else base_link
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            images = sku.get("images", [])
            image_url = images[0].get("imageUrl", "") if images else ""

            price = None
            in_stock = False
            for seller in sku.get("sellers", []):
                offer = seller.get("commertialOffer", {})
                p = offer.get("Price") or offer.get("ListPrice")
                if p and float(p) > 0:
                    price = float(p)
                    in_stock = offer.get("AvailableQuantity", 0) > 0
                    break
            if not price:
                continue

            self.result.products.append(
                PriceData(
                    name=name,
                    url=link,
                    price=price,
                    brand=brand,
                    volume_ml=self.parse_volume(name),
                    image_url=image_url or None,
                    in_stock=in_stock,
                    category="perfume",
                )
            )
