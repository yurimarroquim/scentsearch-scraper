import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

WP_URL = os.getenv("WP_SITE_URL") or os.getenv("WP_URL", "")
WP_USERNAME = os.getenv("WP_USERNAME", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL.startswith("sqlite:///"):
    _db_file = _DATABASE_URL.replace("sqlite:///", "")
    if not os.path.isabs(_db_file):
        DB_PATH = str(BASE_DIR / "data" / _db_file)
    else:
        DB_PATH = _db_file
else:
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "scentsearch.db"))

SCRAPE_HOUR = int(os.getenv("SCHEDULE_HOUR") or os.getenv("SCRAPE_HOUR", "6"))
SCRAPE_MINUTE = int(os.getenv("SCHEDULE_MINUTE") or os.getenv("SCRAPE_MINUTE", "0"))

DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "scentsearch.log"))

REQUEST_DELAY = float(os.getenv("SCRAPE_DELAY") or os.getenv("REQUEST_DELAY", "2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT") or os.getenv("REQUEST_TIMEOUT", "30"))

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
