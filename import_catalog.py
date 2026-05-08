import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.db import init_db, get_db
from database.models import Store, Product

CATALOG = [
    {"name": "Dior Sauvage EDP",          "brand": "Christian Dior",          "volume_ml": 100, "sku": "EDP", "category": "Masculino | Designer"},
    {"name": "Dior Sauvage EDT",          "brand": "Christian Dior",          "volume_ml": 100, "sku": "EDT", "category": "Masculino | Designer"},
    {"name": "Bleu de Chanel EDP",        "brand": "Chanel",                  "volume_ml": 100, "sku": "EDP", "category": "Masculino | Designer"},
    {"name": "Good Girl EDP",             "brand": "Carolina Herrera",         "volume_ml": 80,  "sku": "EDP", "category": "Feminino | Designer"},
    {"name": "212 VIP Men EDT",           "brand": "Carolina Herrera",         "volume_ml": 100, "sku": "EDT", "category": "Masculino | Designer"},
    {"name": "La Vie Est Belle EDP",      "brand": "Lancôme",                 "volume_ml": 75,  "sku": "EDP", "category": "Feminino | Designer"},
    {"name": "Black Opium EDP",           "brand": "Yves Saint Laurent",       "volume_ml": 90,  "sku": "EDP", "category": "Feminino | Designer"},
    {"name": "Invictus EDT",              "brand": "Paco Rabanne",             "volume_ml": 100, "sku": "EDT", "category": "Masculino | Designer"},
    {"name": "1 Million EDT",             "brand": "Paco Rabanne",             "volume_ml": 100, "sku": "EDT", "category": "Masculino | Designer"},
    {"name": "Baccarat Rouge 540 EDP",    "brand": "Maison Francis Kurkdjian", "volume_ml": 70,  "sku": "EDP", "category": "Unissex | Nicho"},
    {"name": "Aventus EDP",               "brand": "Creed",                    "volume_ml": 100, "sku": "EDP", "category": "Masculino | Nicho"},
    {"name": "Malbec EDP",                "brand": "O Boticário",              "volume_ml": 100, "sku": "EDP", "category": "Masculino | Nacional"},
]

def main():
    init_db()

    with get_db() as db:
        catalog_store = db.query(Store).filter(Store.slug == "catalogo").first()
        if not catalog_store:
            catalog_store = Store(
                name="Catálogo Inicial",
                slug="catalogo",
                url="https://scentsearch.com.br",
                is_active=True,
            )
            db.add(catalog_store)
            db.flush()
            print("Loja 'Catálogo Inicial' criada.")

        inserted = 0
        skipped = 0

        for item in CATALOG:
            url = f"https://scentsearch.com.br/catalogo/{item['name'].lower().replace(' ', '-')}"
            exists = db.query(Product).filter(
                Product.store_id == catalog_store.id,
                Product.name == item["name"],
            ).first()

            if exists:
                skipped += 1
                continue

            product = Product(
                store_id=catalog_store.id,
                name=item["name"],
                brand=item["brand"],
                volume_ml=item["volume_ml"],
                sku=item["sku"],
                category=item["category"],
                url=url,
            )
            db.add(product)
            inserted += 1

        db.commit()

    print(f"\nResultado da importação:")
    print(f"  Produtos inseridos : {inserted}")
    print(f"  Já existiam        : {skipped}")
    print(f"  Total no catálogo  : {len(CATALOG)}")

if __name__ == "__main__":
    main()
