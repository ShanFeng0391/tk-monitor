from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tiktok_monitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_default_queue="scrape",
    task_queues={
        "scrape": {"exchange": "scrape", "routing_key": "scrape"},
    },
    task_routes={
        "app.tasks.jobs.*": {"queue": "scrape"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
)
