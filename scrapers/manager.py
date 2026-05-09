import logging
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from scrapers.leloyn import LeLoynScraper
from scrapers.base import ScrapingResult
from scrapers.epoca import EpocaCosmeticosScraper
from scrapers.belezanaweb import BelezaNaWebScraper
from scrapers.amazon import AmazonBrasilScraper
from scrapers.sephora import SephoraBrasilScraper
from scrapers.sieno import SienoPerfumariaScraper
from scrapers.aaz import AAZPerfumesScraper
from scrapers.kingofparfums import KingOfParfumsScraper
from scrapers.pequiperfumes import PequiPerfumesScraper
from scrapers.romaaroma import RomaAromaScraper
from scrapers.opaque import OpaqueScraper
from scrapers.amobeleza import AmobelezaScraper
from scrapers.drogariasaopaulo import DrogariaSaoPauloScraper
from scrapers.kingofDecants import KingOfDecantsScraper
from scrapers.anmy import AnmyScraper
from scrapers.bhdecants import BhDecantsScraper
from scrapers.macdecants import MacDecantsScraper
from scrapers.sgimportados import SgImportadosScraper
from scrapers.decantslondrina import DecantsLondrinaScraper
from scrapers.beautybox import BeautyboxScraper
from scrapers.neeche import NeecheScraper
from scrapers.ofertasna import OfertasNaScraper
from scrapers.guidodecants import GuidoDecantsScraper
from scrapers.giraofertas import GiraoFertasScraper
from database.db import get_db
from database.models import ScrapingLog, Store as StoreModel
from database.repository import (
    StoreRepository, ProductRepository, PriceRepository, ScrapingLogRepository
)

logger = logging.getLogger(__name__)

SCRAPER_REGISTRY = {
    "leloyn": LeLoynScraper,
    "epoca": EpocaCosmeticosScraper,
    "belezanaweb": BelezaNaWebScraper,
    "amazon": AmazonBrasilScraper,
    "sephora": SephoraBrasilScraper,
    "sieno": SienoPerfumariaScraper,
    "aaz": AAZPerfumesScraper,
    "kingofparfums": KingOfParfumsScraper,
    "pequiperfumes": PequiPerfumesScraper,
    "romaaroma": RomaAromaScraper,
    "opaque": OpaqueScraper,
    "amobeleza": AmobelezaScraper,
    "drogariasaopaulo": DrogariaSaoPauloScraper,
    "kingofDecants": KingOfDecantsScraper,
    "bhdecants": BhDecantsScraper,
    "macdecants": MacDecantsScraper,
    "sgimportados": SgImportadosScraper,
    "decantslondrina": DecantsLondrinaScraper,
    "beautybox": BeautyboxScraper,
    "anmy": AnmyScraper,
    "neeche": NeecheScraper,
    "ofertasna": OfertasNaScraper,
    "guidodecants": GuidoDecantsScraper,
    "giraofertas": GiraoFertasScraper,
}


class ScrapingManager:
    def __init__(self):
        pass

    def run_all(self) -> list[dict]:
        results = []

        with get_db() as db:
            store_repo = StoreRepository(db)
            stores = store_repo.get_all_active()
            store_slugs = [s.slug for s in stores]

        for slug in store_slugs:
            if slug not in SCRAPER_REGISTRY:
                logger.warning(f"No scraper found for store: {slug}")
                continue

            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.run_store, slug)
                    result = future.result(timeout=300)
                    results.append(result)
            except FuturesTimeoutError:
                logger.error(f"Scraper '{slug}' exceeded 300s timeout — skipping.")
                results.append({"store": slug, "products_found": 0, "prices_saved": 0, "errors": 1, "duration_seconds": 120})
            except Exception as e:
                logger.error(f"Scraper '{slug}' raised unexpected error: {e}", exc_info=True)
                results.append({"store": slug, "products_found": 0, "prices_saved": 0, "errors": 1, "duration_seconds": 0})

        logger.info(f"Completed scraping all stores. Total: {len(results)} stores.")
        return results

    def run_store(self, store_slug: str) -> dict:
        scraper_class = SCRAPER_REGISTRY.get(store_slug)
        if not scraper_class:
            return {"error": f"No scraper for {store_slug}"}

        log_id = None

        with get_db() as db:
            store_repo = StoreRepository(db)
            store = store_repo.get_by_slug(store_slug)
            if not store:
                store = StoreModel(
                    slug=store_slug,
                    name=scraper_class.store_name,
                    url=getattr(scraper_class, 'base_url', ''),
                    active=True,
                )
                db.add(store)
                db.commit()
                db.refresh(store)
                logger.info(f"Loja '{store_slug}' criada automaticamente no banco.")

            store_id = store.id
            store_name = store.name

            log_repo = ScrapingLogRepository(db)
            log = log_repo.create(store_id, store_name)
            db.flush()
            log_id = log.id
            db.commit()

        scraper = scraper_class()
        result: ScrapingResult = scraper.run()

        saved_prices = 0
        with get_db() as db:
            product_repo = ProductRepository(db)
            price_repo = PriceRepository(db)

            for price_data in result.products:
                try:
                    product, created = product_repo.get_or_create(
                        store_id=store_id,
                        url=price_data.url,
                        name=price_data.name,
                        brand=price_data.brand,
                        volume_ml=price_data.volume_ml,
                        sku=price_data.sku,
                        image_url=price_data.image_url,
                        category=price_data.category,
                    )

                    if price_data.price is None:
                        continue
                    price_repo.add(
                        product_id=product.id,
                        price=price_data.price,
                        original_price=price_data.original_price,
                        discount_percent=price_data.discount_percent,
                        in_stock=price_data.in_stock,
                    )
                    saved_prices += 1
                except Exception as e:
                    logger.error(f"Error saving product {price_data.name}: {e}")
                    result.errors += 1

            if log_id:
                log = db.query(ScrapingLog).filter(ScrapingLog.id == log_id).first()
                if log:
                    log_repo = ScrapingLogRepository(db)
                    log_repo.finish(
                        log=log,
                        products_found=len(result.products),
                        prices_updated=saved_prices,
                        errors=result.errors,
                        status="success" if result.errors == 0 else "partial",
                    )
            db.commit()

        return {
            "store": store_slug,
            "store_name": store_name,
            "products_found": len(result.products),
            "prices_saved": saved_prices,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }

    def get_available_scrapers(self) -> list[str]:
        return list(SCRAPER_REGISTRY.keys())
