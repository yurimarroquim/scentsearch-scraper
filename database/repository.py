import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Store, Product, Price, ScrapingLog, WordPressSync

logger = logging.getLogger(__name__)


class StoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_active(self):
        return self.db.query(Store).filter(Store.is_active == True).all()

    def get_by_slug(self, slug: str) -> Optional[Store]:
        return self.db.query(Store).filter(Store.slug == slug).first()

    def get_by_id(self, store_id: int) -> Optional[Store]:
        return self.db.query(Store).filter(Store.id == store_id).first()


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, store_id: int, url: str, name: str, **kwargs) -> tuple[Product, bool]:
        product = self.db.query(Product).filter(
            Product.store_id == store_id,
            Product.url == url
        ).first()

        if product:
            product.name = name
            product.updated_at = datetime.utcnow()
            for key, value in kwargs.items():
                if value is not None:
                    setattr(product, key, value)
            return product, False

        product = Product(store_id=store_id, url=url, name=name, **kwargs)
        self.db.add(product)
        self.db.flush()
        return product, True

    def get_all(self, limit: int = 100, offset: int = 0):
        return self.db.query(Product).offset(offset).limit(limit).all()

    def get_by_store(self, store_id: int):
        return self.db.query(Product).filter(Product.store_id == store_id).all()

    def search(self, query: str, limit: int = 50):
        return self.db.query(Product).filter(
            Product.name.ilike(f"%{query}%")
        ).limit(limit).all()

    def count_total(self) -> int:
        return self.db.query(func.count(Product.id)).scalar()


class PriceRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, product_id: int, price: float, **kwargs) -> Price:
        price_record = Price(product_id=product_id, price=price, **kwargs)
        self.db.add(price_record)
        self.db.flush()
        return price_record

    def get_latest(self, product_id: int) -> Optional[Price]:
        return self.db.query(Price).filter(
            Price.product_id == product_id
        ).order_by(Price.scraped_at.desc()).first()

    def get_history(self, product_id: int, days: int = 30):
        since = datetime.utcnow() - timedelta(days=days)
        return self.db.query(Price).filter(
            Price.product_id == product_id,
            Price.scraped_at >= since
        ).order_by(Price.scraped_at.asc()).all()

    def get_lowest(self, product_id: int) -> Optional[Price]:
        return self.db.query(Price).filter(
            Price.product_id == product_id
        ).order_by(Price.price.asc()).first()

    def count_today(self) -> int:
        today = datetime.utcnow().date()
        return self.db.query(func.count(Price.id)).filter(
            func.date(Price.scraped_at) == today
        ).scalar()


class ScrapingLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, store_id: int, store_name: str) -> ScrapingLog:
        log = ScrapingLog(store_id=store_id, store_name=store_name)
        self.db.add(log)
        self.db.flush()
        return log

    def finish(self, log: ScrapingLog, products_found: int, prices_updated: int,
               errors: int, status: str = "success", error_message: str = None):
        log.finished_at = datetime.utcnow()
        log.products_found = products_found
        log.prices_updated = prices_updated
        log.errors = errors
        log.status = status
        log.error_message = error_message
        self.db.flush()

    def get_recent(self, limit: int = 50):
        return self.db.query(ScrapingLog).order_by(
            ScrapingLog.started_at.desc()
        ).limit(limit).all()

    def get_last_run_per_store(self):
        subq = self.db.query(
            ScrapingLog.store_name,
            func.max(ScrapingLog.started_at).label("last_run")
        ).group_by(ScrapingLog.store_name).subquery()

        return self.db.query(ScrapingLog).join(
            subq,
            (ScrapingLog.store_name == subq.c.store_name) &
            (ScrapingLog.started_at == subq.c.last_run)
        ).all()
