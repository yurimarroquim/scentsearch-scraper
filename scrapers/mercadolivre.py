import logging
import time
from scrapers.base import BaseScraper, ScrapingResult, PriceData
from auth import ml_oauth

logger = logging.getLogger(__name__)

PAGE_SIZE = 50
MAX_PAGES = 6

SEARCH_QUERIES = [
    "perfume eau de parfum masculino",
    "perfume eau de parfum feminino",
    "perfume eau de toilette masculino",
    "perfume eau de toilette feminino",
]

ML_CATEGORY_PERFUME = "MLB1246"


class MercadoLivreScraper(BaseScraper):
    store_name = "Mercado Livre"
    store_slug = "mercadolivre"
    base_url = "https://www.mercadolivre.com.br"
    API_BASE = "https://api.mercadolibre.com"

    def scrape(self) -> ScrapingResult:
        status = ml_oauth.get_token_status()

        if status["status"] == "not_configured":
            logger.warning(
                "[MercadoLivre] ML_CLIENT_ID / ML_CLIENT_SECRET não configurados. "
                "Acesse /integrations no dashboard para configurar."
            )
            return self.result

        if status["status"] == "not_authorized":
            logger.warning(
                "[MercadoLivre] App configurado mas ainda não autorizado pelo usuário. "
                "Acesse /integrations no dashboard e clique em 'Autorizar no Mercado Livre'."
            )
            return self.result

        token = ml_oauth.get_valid_access_token()
        if not token:
            logger.error("[MercadoLivre] Não foi possível obter token válido.")
            return self.result

        seen_ids: set[str] = set()
        auth_headers = {"Authorization": f"Bearer {token}"}

        for query in SEARCH_QUERIES:
            for page in range(MAX_PAGES):
                offset = page * PAGE_SIZE
                params = {
                    "q": query,
                    "category": ML_CATEGORY_PERFUME,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "sort": "price_asc",
                }
                try:
                    r = self.session.get(
                        f"{self.API_BASE}/sites/MLB/search",
                        params=params,
                        headers=auth_headers,
                        timeout=(5, 15),
                    )
                    if r.status_code == 401:
                        logger.error("[MercadoLivre] Token expirado ou inválido.")
                        return self.result
                    if r.status_code != 200:
                        logger.warning(f"[MercadoLivre] HTTP {r.status_code} na busca.")
                        break

                    data = r.json()
                    items = data.get("results", [])
                    paging = data.get("paging", {})
                    total = paging.get("total", 0)

                    count = 0
                    for item in items:
                        item_id = item.get("id", "")
                        if item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)
                        try:
                            parsed = self._parse_item(item)
                            if parsed:
                                self.result.products.append(parsed)
                                count += 1
                        except Exception as e:
                            logger.warning(f"Erro ao parsear item {item_id}: {e}")
                            self.result.errors += 1

                    logger.info(
                        f"[MercadoLivre] '{query}' p.{page+1}: {count} novos "
                        f"(total={total})"
                    )

                    if offset + PAGE_SIZE >= total or not items:
                        break

                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"[MercadoLivre] Erro na requisição: {e}")
                    break

        return self.result

    def _parse_item(self, item: dict) -> PriceData | None:
        title = item.get("title", "").strip()
        if not title:
            return None

        price = item.get("price")
        if not price or price <= 0:
            return None

        url = item.get("permalink", "")
        if not url:
            item_id = item.get("id", "")
            url = f"https://produto.mercadolivre.com.br/{item_id}"

        original_price = item.get("original_price")
        if original_price and original_price <= price:
            original_price = None

        discount = round((1 - price / original_price) * 100, 1) if original_price else None

        thumbnail = item.get("thumbnail", "").replace("I.jpg", "O.jpg")
        in_stock = item.get("available_quantity", 1) > 0
        volume_ml = self.parse_volume(title)

        brand = None
        for attr in item.get("attributes", []):
            if attr.get("id") == "BRAND":
                brand = attr.get("value_name")
                break

        return PriceData(
            name=title,
            url=url,
            price=price,
            brand=brand,
            volume_ml=volume_ml,
            original_price=original_price,
            discount_percent=discount,
            image_url=thumbnail or None,
            in_stock=in_stock,
            category=self.category,
        )
