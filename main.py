import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import LOG_LEVEL, LOG_FILE
import uvicorn

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)

logger = logging.getLogger(__name__)


def main():
    port = int(os.environ.get("PORT", os.environ.get("DASHBOARD_PORT", "8000")))
    host = "0.0.0.0"

    logger.info(f"Starting ScentSearch Scraper on {host}:{port}...")
    uvicorn.run(
        "dashboard.app:app",
        host=host,
        port=port,
        reload=False,
        log_level=LOG_LEVEL.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
