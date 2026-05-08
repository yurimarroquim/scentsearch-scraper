import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from config.settings import SCRAPE_HOUR, SCRAPE_MINUTE
from scheduler.tasks import run_daily_scraping

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=2)}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        }

        _scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )

    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()

    existing_jobs = {job.id for job in scheduler.get_jobs()}
    if "daily_scraping" not in existing_jobs:
        scheduler.add_job(
            run_daily_scraping,
            trigger=CronTrigger(
                hour=SCRAPE_HOUR, minute=SCRAPE_MINUTE, timezone="America/Sao_Paulo"
            ),
            id="daily_scraping",
            name="Daily Price Scraping",
            replace_existing=True,
        )
        logger.info(
            f"Scheduled daily scraping at {SCRAPE_HOUR:02d}:{SCRAPE_MINUTE:02d}"
        )

    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")

    return scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_jobs_info() -> list[dict]:
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            }
        )
    return jobs


def trigger_now(job_id: str = "daily_scraping") -> bool:
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if job:
        scheduler.modify_job(job_id, next_run_time=None)
        job.modify(next_run_time=None)
        from datetime import datetime

        scheduler.get_job(job_id).modify(next_run_time=datetime.now())
        return True
    return False
