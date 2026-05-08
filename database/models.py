from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="store")

    def __repr__(self):
        return f"<Store(name={self.name})>"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    name = Column(String(500), nullable=False)
    brand = Column(String(200))
    volume_ml = Column(Integer)
    sku = Column(String(200))
    url = Column(String(2000), nullable=False)
    image_url = Column(String(2000))
    category = Column(String(100), default="perfume")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("Store", back_populates="products")
    prices = relationship("Price", back_populates="product", order_by="Price.scraped_at.desc()")

    __table_args__ = (
        Index("idx_product_store", "store_id"),
        Index("idx_product_sku", "sku"),
    )

    def __repr__(self):
        return f"<Product(name={self.name[:50]})>"


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    original_price = Column(Float)
    discount_percent = Column(Float)
    in_stock = Column(Boolean, default=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="prices")

    __table_args__ = (
        Index("idx_price_product", "product_id"),
        Index("idx_price_scraped_at", "scraped_at"),
    )

    def __repr__(self):
        return f"<Price(price={self.price}, scraped_at={self.scraped_at})>"


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"))
    store_name = Column(String(100))
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    products_found = Column(Integer, default=0)
    prices_updated = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    status = Column(String(50), default="running")
    error_message = Column(Text)

    def __repr__(self):
        return f"<ScrapingLog(store={self.store_name}, status={self.status})>"


class WordPressSync(Base):
    __tablename__ = "wordpress_syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    wp_post_id = Column(Integer)
    last_synced = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending")
    error_message = Column(Text)

    def __repr__(self):
        return f"<WordPressSync(product_id={self.product_id}, status={self.status})>"
