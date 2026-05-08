import logging
from scrapers.base import BaseScraper, ScrapingResult, PriceData

logger = logging.getLogger(__name__)


class BeautyboxScraper(BaseScraper):
    store_name = "Beautybox"
    store_slug = "beautybox"
    base_url = "https://www.beautybox.com.br"

    def scrape(self) -> ScrapingResult:
        logger.warning(
            "[Beautybox] Site inacessível (TCP timeout em todas as tentativas). "
            "Scraping desativado temporariamente."
        )
        return self.result
