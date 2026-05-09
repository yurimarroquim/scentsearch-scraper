import os, sys

store_slug = os.environ.get('STORE_SLUG')
if not store_slug:
    print("STORE_SLUG não definido")
    sys.exit(1)

print(f"Iniciando scrape: {store_slug}")

from database.db import engine
from database.models import Base
Base.metadata.create_all(bind=engine)

from scheduler.tasks import run_store_scraping
run_store_scraping(store_slug)

from lovable_integration.sync import LovableSyncService
svc = LovableSyncService()
result = svc.sync_all_products(limit=99999)
total = result.get('synced', 0) if isinstance(result, dict) else 0

print(f"Concluído: {store_slug} — {total} produtos sincronizados")
