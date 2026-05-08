import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from database.db import init_db, get_db
from database.models import Store, Product, Price, ScrapingLog
from database.repository import (
    StoreRepository, ProductRepository, PriceRepository, ScrapingLogRepository
)
from scheduler.scheduler import start_scheduler, stop_scheduler, get_jobs_info
from scheduler.tasks import run_daily_scraping, run_store_scraping
from wordpress.client import WordPressClient
from wordpress.sync import WordPressSyncService
from auth import ml_oauth

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("ScentSearch Scraper started")
    yield
    stop_scheduler()
    logger.info("ScentSearch Scraper stopped")


app = FastAPI(
    title="ScentSearch Scraper",
    description="Sistema de monitoramento de preços de perfumes",
    lifespan=lifespan,
)


def _get_stats() -> dict:
    with get_db() as db:
        total_products = db.query(func.count(Product.id)).scalar() or 0
        active_stores = db.query(func.count(Store.id)).filter(Store.is_active == True).scalar() or 0
        total_logs = db.query(func.count(ScrapingLog.id)).scalar() or 0
        from datetime import date
        today = date.today()
        prices_today = db.query(func.count(Price.id)).filter(
            func.date(Price.scraped_at) == today
        ).scalar() or 0

    return {
        "total_products": total_products,
        "active_stores": active_stores,
        "total_logs": total_logs,
        "prices_today": prices_today,
    }


@app.get("/ping")
@app.head("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stats = _get_stats()
    jobs = get_jobs_info()

    with get_db() as db:
        log_repo = ScrapingLogRepository(db)
        last_runs = log_repo.get_last_run_per_store()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stats": stats,
            "jobs": jobs,
            "last_runs": last_runs,
            "active_page": "dashboard",
        },
    )


@app.get("/stores", response_class=HTMLResponse)
async def stores_page(request: Request, message: str = None, message_type: str = "success"):
    with get_db() as db:
        store_repo = StoreRepository(db)
        stores = store_repo.get_all_active()

    return templates.TemplateResponse(
        request=request,
        name="stores.html",
        context={
            "stores": stores,
            "message": message,
            "message_type": message_type,
            "active_page": "stores",
        },
    )


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request, q: str = None, offset: int = 0):
    with get_db() as db:
        if q:
            products = db.query(Product).filter(
                Product.name.ilike(f"%{q}%")
            ).offset(offset).limit(50).all()
            total = db.query(func.count(Product.id)).filter(
                Product.name.ilike(f"%{q}%")
            ).scalar()
        else:
            products = db.query(Product).offset(offset).limit(50).all()
            total = db.query(func.count(Product.id)).scalar()

        items = []
        for product in products:
            latest_price = db.query(Price).filter(
                Price.product_id == product.id
            ).order_by(Price.scraped_at.desc()).first()

            store = db.query(Store).filter(Store.id == product.store_id).first()

            items.append({
                "product": product,
                "latest_price": latest_price,
                "store_name": store.name if store else "Unknown",
            })

    return templates.TemplateResponse(
        request=request,
        name="products.html",
        context={
            "products": items,
            "total": total,
            "offset": offset,
            "query": q,
            "active_page": "products",
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    with get_db() as db:
        log_repo = ScrapingLogRepository(db)
        logs = log_repo.get_recent(limit=100)

    return templates.TemplateResponse(
        request=request,
        name="logs.html",
        context={"logs": logs, "active_page": "logs"},
    )


@app.get("/wordpress", response_class=HTMLResponse)
async def wordpress_page(request: Request, message: str = None, message_type: str = "success"):
    wp_client = WordPressClient()
    wp_configured = wp_client.is_configured()
    wp_connected = wp_client.test_connection() if wp_configured else False

    return templates.TemplateResponse(
        request=request,
        name="wordpress.html",
        context={
            "wp_configured": wp_configured,
            "wp_connected": wp_connected,
            "message": message,
            "message_type": message_type,
            "active_page": "wordpress",
        },
    )


def _run_scraping_bg(store_slug: str = None):
    if store_slug:
        run_store_scraping(store_slug)
    else:
        run_daily_scraping()


@app.post("/scrape/all")
async def scrape_all(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_scraping_bg)
    return RedirectResponse(
        url="/?message=Scraping+iniciado+para+todas+as+lojas",
        status_code=303,
    )


@app.post("/scrape/{store_slug}")
async def scrape_store(store_slug: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_scraping_bg, store_slug)
    return RedirectResponse(
        url=f"/stores?message=Scraping+iniciado+para+{store_slug}",
        status_code=303,
    )


@app.post("/wordpress/sync")
async def wordpress_sync(background_tasks: BackgroundTasks):
    def _sync():
        svc = WordPressSyncService()
        svc.sync_all_products()

    background_tasks.add_task(_sync)
    return RedirectResponse(
        url="/wordpress?message=Sincronização+iniciada",
        status_code=303,
    )


@app.get("/api/stats")
async def api_stats():
    return _get_stats()


@app.get("/api/jobs")
async def api_jobs():
    return get_jobs_info()


@app.get("/api/stores")
async def api_stores():
    with get_db() as db:
        store_repo = StoreRepository(db)
        stores = store_repo.get_all_active()
        return [{"id": s.id, "name": s.name, "slug": s.slug, "url": s.url} for s in stores]


# ── Integrations page ────────────────────────────────────────────────────────

@app.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, message: str = None, message_type: str = "success"):
    client_id = os.getenv("ML_CLIENT_ID", "")
    client_secret = os.getenv("ML_CLIENT_SECRET", "")

    def _preview(val: str, keep: int = 6) -> str:
        if not val:
            return "(não configurado)"
        return val[:keep] + "•" * max(0, len(val) - keep)

    amazon_access = os.getenv("AMAZON_ACCESS_KEY", "")
    amazon_secret = os.getenv("AMAZON_SECRET_KEY", "")
    amazon_tag = os.getenv("AMAZON_PARTNER_TAG", "")

    return templates.TemplateResponse(
        request=request,
        name="integrations.html",
        context={
            "active_page": "integrations",
            "message": message,
            "message_type": message_type,
            "ml_status": ml_oauth.get_token_status(),
            "ml_auth_url": ml_oauth.get_authorization_url(),
            "ml_client_id_preview": _preview(client_id),
            "ml_secret_preview": _preview(client_secret),
            "amazon_configured": bool(amazon_access and amazon_secret and amazon_tag),
            "amazon_access_key": bool(amazon_access),
            "amazon_secret_key": bool(amazon_secret),
            "amazon_partner_tag": bool(amazon_tag),
        },
    )


# ── Mercado Livre OAuth routes ────────────────────────────────────────────────

@app.get("/mercadolivre/authorize")
async def ml_authorize():
    """Redireciona direto para a página de autorização do Mercado Livre."""
    return RedirectResponse(url=ml_oauth.get_authorization_url())


@app.post("/mercadolivre/exchange")
async def ml_exchange(request: Request):
    """Recebe o código copiado pelo usuário da URL de callback e troca por token."""
    from fastapi import Form
    form = await request.form()
    code = (form.get("code") or "").strip()

    if not code:
        return RedirectResponse(
            url="/integrations?message=Código+não+informado&message_type=error",
            status_code=303,
        )

    token_data = ml_oauth.exchange_code_for_token(code)
    if not token_data:
        return RedirectResponse(
            url="/integrations?message=Código+inválido+ou+expirado.+Repita+o+processo+de+autorização.&message_type=error",
            status_code=303,
        )

    user_id = token_data.get("user_id", "")
    return RedirectResponse(
        url=f"/integrations?message=Mercado+Livre+autorizado+com+sucesso!+(user_id%3D{user_id})",
        status_code=303,
    )


@app.get("/mercadolivre/callback", response_class=HTMLResponse)
async def ml_callback(request: Request, code: str = None, error: str = None):
    """Callback automático — usado se o redirect_uri apontar para este servidor."""
    if error or not code:
        return RedirectResponse(
            url="/integrations?message=Autorização+cancelada+ou+erro+no+ML&message_type=error",
            status_code=303,
        )
    token_data = ml_oauth.exchange_code_for_token(code)
    if not token_data:
        return RedirectResponse(
            url="/integrations?message=Falha+ao+obter+token+do+Mercado+Livre&message_type=error",
            status_code=303,
        )
    user_id = token_data.get("user_id", "")
    return RedirectResponse(
        url=f"/integrations?message=Mercado+Livre+autorizado!+(user_id%3D{user_id})",
        status_code=303,
    )


@app.post("/mercadolivre/revoke")
async def ml_revoke():
    ml_oauth.delete_token()
    return RedirectResponse(
        url="/integrations?message=Token+do+Mercado+Livre+removido",
        status_code=303,
    )
