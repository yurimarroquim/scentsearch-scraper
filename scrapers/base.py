import logging
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

from config.settings import REQUEST_DELAY, MAX_RETRIES, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    name: str
    url: str
    price: float
    brand: Optional[str] = None
    volume_ml: Optional[int] = None
    sku: Optional[str] = None
    image_url: Optional[str] = None
    original_price: Optional[float] = None
    discount_percent: Optional[float] = None
    in_stock: bool = True
    category: str = "perfume"
    tipo: str = "frasco"
    scraped_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScrapingResult:
    store_slug: str
    store_name: str
    products: list[PriceData] = field(default_factory=list)
    errors: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    def finish(self):
        self.finished_at = datetime.utcnow()

    @property
    def duration_seconds(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0


class BaseScraper(ABC):
    store_name: str = ""
    store_slug: str = ""
    base_url: str = ""
    category: str = "perfume"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    def __init__(self):
        self.session = cf_requests.Session(impersonate="chrome124")
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.result = ScrapingResult(
            store_slug=self.store_slug,
            store_name=self.store_name,
        )

    def get_page(self, url: str, params: dict = None) -> Optional[BeautifulSoup]:
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                status = response.status_code

                if status == 200:
                    pass
                    return BeautifulSoup(response.text, "lxml")
                elif status == 429:
                    wait = (attempt + 1) * 5
                    logger.warning(f"Rate limited on {url}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif status in (400, 403, 404):
                    logger.warning(f"HTTP error on {url}: {status} Client Error")
                    self.result.errors += 1
                    return None
                elif status in (500, 502, 503):
                    logger.warning(f"HTTP {status} server error on {url}")
                else:
                    logger.warning(f"HTTP error on {url}: {status}")

            except Exception as e:
                err = str(e).lower()
                if "timeout" in err:
                    logger.warning(f"Timeout on {url} (attempt {attempt + 1})")
                elif "connection" in err or "resolve" in err:
                    logger.warning(f"Connection error on {url}: {e}")
                    return None
                else:
                    logger.error(f"Unexpected error on {url}: {e}")
                    return None

            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))

        self.result.errors += 1
        return None

    def delay(self, extra: float = 0):
        time.sleep(REQUEST_DELAY + random.uniform(0, 1) + extra)

    def parse_price(self, price_str: str) -> Optional[float]:
        if not price_str:
            return None
        try:
            cleaned = (
                price_str.replace("R$", "").replace(".", "").replace(",", ".").strip()
            )
            return float(cleaned)
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse price: {price_str!r}")
            return None

    def parse_volume(self, text: str) -> Optional[int]:
        if not text:
            return None
        import re

        match = re.search(r"(\d+)\s*ml", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @abstractmethod
    def scrape(self) -> ScrapingResult:
        pass

    def run(self) -> ScrapingResult:
        logger.info(f"Starting scrape for {self.store_name}")
        try:
            result = self.scrape()
            result.finish()
            logger.info(
                f"Finished scraping {self.store_name}: "
                f"{len(result.products)} products, {result.errors} errors, "
                f"{result.duration_seconds:.1f}s"
            )
            return result
        except Exception as e:
            logger.error(f"Fatal error scraping {self.store_name}: {e}", exc_info=True)
            self.result.errors += 1
            self.result.finish()
            return self.result
