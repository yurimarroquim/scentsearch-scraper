import logging
import time
import hmac
import hashlib
import json
from datetime import datetime, timezone
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)

SEARCH_KEYWORDS = [
    "perfume masculino eau de parfum",
    "perfume feminino eau de parfum",
    "perfume masculino eau de toilette",
    "perfume feminino eau de toilette",
]


class AmazonBrasilScraper(BaseScraper):
    store_name = "Amazon Brasil"
    store_slug = "amazon"
    base_url = "https://www.amazon.com.br"

    PA_HOST = "webservices.amazon.com.br"
    PA_REGION = "us-east-1"
    PA_SERVICE = "ProductAdvertisingAPI"
    PA_ENDPOINT = "https://webservices.amazon.com.br/paapi5/searchitems"

    def __init__(self):
        super().__init__()
        import os
        self._access_key = os.getenv("AMAZON_ACCESS_KEY", "")
        self._secret_key = os.getenv("AMAZON_SECRET_KEY", "")
        self._partner_tag = os.getenv("AMAZON_PARTNER_TAG", "")

        if not all([self._access_key, self._secret_key, self._partner_tag]):
            logger.warning(
                "[Amazon] Credenciais da Product Advertising API não configuradas. "
                "Cadastre-se em https://programas.amazon.com.br/associates e adicione "
                "AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY e AMAZON_PARTNER_TAG nas "
                "variáveis de ambiente."
            )

    def _is_configured(self) -> bool:
        return bool(self._access_key and self._secret_key and self._partner_tag)

    def scrape(self) -> ScrapingResult:
        if not self._is_configured():
            logger.warning("[Amazon] Credenciais ausentes — scraping ignorado.")
            return self.result

        seen_asins: set[str] = set()

        for keyword in SEARCH_KEYWORDS:
            try:
                items = self._search_items(keyword)
                count = 0
                for item in items:
                    asin = item.get("ASIN", "")
                    if asin in seen_asins:
                        continue
                    seen_asins.add(asin)
                    try:
                        parsed = self._parse_pa_item(item)
                        if parsed:
                            self.result.products.append(parsed)
                            count += 1
                    except Exception as e:
                        logger.warning(f"Erro ao parsear ASIN {asin}: {e}")
                        self.result.errors += 1

                logger.info(f"[Amazon] '{keyword}': {count} novos produtos")
                time.sleep(1)

            except Exception as e:
                logger.error(f"[Amazon] Erro na busca '{keyword}': {e}")
                self.result.errors += 1

        return self.result

    def _search_items(self, keyword: str) -> list[dict]:
        payload = {
            "PartnerTag": self._partner_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.com.br",
            "Keywords": keyword,
            "SearchIndex": "Beauty",
            "Resources": [
                "ItemInfo.Title",
                "ItemInfo.ByLineInfo",
                "Offers.Listings.Price",
                "Offers.Listings.SavingBasis",
                "Offers.Listings.Availability.Message",
                "Images.Primary.Medium",
            ],
            "SortBy": "Price:LowToHigh",
            "ItemCount": 10,
        }

        payload_json = json.dumps(payload, separators=(",", ":"))
        headers = self._build_signed_headers(payload_json)

        r = self.session.post(
            self.PA_ENDPOINT,
            data=payload_json,
            headers=headers,
            timeout=(5, 20),
        )

        if r.status_code != 200:
            logger.error(f"[Amazon PA API] HTTP {r.status_code}: {r.text[:300]}")
            return []

        data = r.json()
        return data.get("SearchResult", {}).get("Items", [])

    def _build_signed_headers(self, payload: str) -> dict:
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        headers_map = {
            "content-encoding": "amz-1.0",
            "content-type": "application/json; charset=utf-8",
            "host": self.PA_HOST,
            "x-amz-date": amz_date,
            "x-amz-target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
        }

        canonical_headers = "".join(
            f"{k}:{v}\n" for k, v in sorted(headers_map.items())
        )
        signed_headers_str = ";".join(sorted(headers_map.keys()))
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        canonical_request = "\n".join([
            "POST", "/paapi5/searchitems", "",
            canonical_headers, signed_headers_str, payload_hash,
        ])

        credential_scope = f"{date_stamp}/{self.PA_REGION}/{self.PA_SERVICE}/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        def _sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        signing_key = _sign(
            _sign(_sign(_sign(
                ("AWS4" + self._secret_key).encode("utf-8"), date_stamp),
                self.PA_REGION), self.PA_SERVICE),
            "aws4_request",
        )

        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers_str}, Signature={signature}"
        )

        return {**headers_map, "Authorization": authorization}

    def _parse_pa_item(self, item: dict) -> PriceData | None:
        title = (
            item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "").strip()
        )
        if not title:
            return None

        asin = item.get("ASIN", "")
        url = f"{self.base_url}/dp/{asin}"

        listings = item.get("Offers", {}).get("Listings", [])
        if not listings:
            return None

        listing = listings[0]
        price_info = listing.get("Price", {})
        price = price_info.get("Amount")
        if not price or price <= 0:
            return None

        saving_basis = listing.get("SavingBasis", {})
        original_price = saving_basis.get("Amount") if saving_basis else None
        if original_price and original_price <= price:
            original_price = None

        discount = round((1 - price / original_price) * 100, 1) if original_price else None

        availability = listing.get("Availability", {}).get("Message", "")
        in_stock = not availability or "disponível" in availability.lower()

        image_url = (
            item.get("Images", {}).get("Primary", {}).get("Medium", {}).get("URL")
        )

        brand = (
            item.get("ItemInfo", {})
            .get("ByLineInfo", {})
            .get("Brand", {})
            .get("DisplayValue")
        )

        return PriceData(
            name=title, url=url, price=price, brand=brand,
            volume_ml=self.parse_volume(title), sku=asin,
            original_price=original_price, discount_percent=discount,
            image_url=image_url, in_stock=in_stock, category=self.category,
        )
