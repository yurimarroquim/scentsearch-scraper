import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from config.settings import DB_PATH
from database.models import Base, Store

logger = logging.getLogger(__name__)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(bind=engine)
    _seed_stores()
    logger.info("Database initialized successfully")


def _seed_stores():
    stores_data = [
        {"name": "Época Cosméticos", "slug": "epoca", "url": "https://www.epocacosmeticos.com.br"},
        {"name": "Beleza na Web", "slug": "belezanaweb", "url": "https://www.belezanaweb.com.br"},
        {"name": "Amazon Brasil", "slug": "amazon", "url": "https://www.amazon.com.br"},
        {"name": "Mercado Livre", "slug": "mercadolivre", "url": "https://www.mercadolivre.com.br"},
        {"name": "Sephora Brasil", "slug": "sephora", "url": "https://www.sephora.com.br"},
        {"name": "Sieno Perfumaria", "slug": "sieno", "url": "https://www.sieno.com.br"},
        {"name": "AAZ Perfumes", "slug": "aaz", "url": "https://www.aazperfumes.com.br"},
        {"name": "Shoptime", "slug": "shoptime", "url": "https://www.shoptime.com.br"},
        {"name": "The King of Parfums", "slug": "kingofparfums", "url": "https://www.thekingofparfums.com.br"},
        {"name": "Beautybox", "slug": "beautybox", "url": "https://www.beautybox.com.br"},
    ]

    with get_db() as db:
        for store_data in stores_data:
            existing = db.query(Store).filter(Store.slug == store_data["slug"]).first()
            if not existing:
                store = Store(**store_data)
                db.add(store)
        db.commit()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    return SessionLocal()
