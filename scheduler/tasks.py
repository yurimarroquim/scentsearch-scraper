import logging
from datetime import datetime

from scrapers.manager import ScrapingManager
from lovable_integration.sync import LovableSyncService

logger = logging.getLogger(__name__)


def run_daily_scraping():
    logger.info(f"=== Iniciando scraping diário em {datetime.now().isoformat()} ===")
    manager = ScrapingManager()

    try:
        results = manager.run_all()
        total_products = sum(r.get("products_found", 0) for r in results)
        total_prices = sum(r.get("prices_saved", 0) for r in results)
        total_errors = sum(r.get("errors", 0) for r in results)

        logger.info(
            f"=== Scraping completo: "
            f"{total_products} produtos, {total_prices} preços salvos, "
            f"{total_errors} erros ==="
        )

        # Sync Lovable
        logger.info("Iniciando sync com Lovable...")
        lovable_service = LovableSyncService()
        if lovable_service.is_available():
            total_synced = 0
            for _ in range(500):
                lovable_result = lovable_service.sync_all_products(limit=500)
                synced = lovable_result.get("synced", 0)
                total_synced += synced
                if synced == 0:
                    break
            logger.info(f"Lovable sync completo: {total_synced} produtos sincronizados")
        else:
            logger.info("Lovable sync ignorado (não configurado)")

        return {
            "status": "success",
            "total_products": total_products,
            "total_prices": total_prices,
            "total_errors": total_errors,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Erro fatal no scraping: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def run_store_scraping(store_slug: str) -> dict:
    logger.info(f"Rodando scraping da loja: {store_slug}")
    manager = ScrapingManager()
    result = manager.run_store(store_slug)
    logger.info(f"Scraping da loja completo: {result}")
    return result
