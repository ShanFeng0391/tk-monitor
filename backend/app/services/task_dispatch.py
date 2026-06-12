"""混合部署下统一走 Celery Worker 池，避免 API/Beat 进程内串行扫全库。"""
from __future__ import annotations

from app.config import get_settings

settings = get_settings()


def use_worker_pool() -> bool:
    return not settings.local_mode


def dispatch_scrape_creator(
    creator_id: int,
    mode: str,
    *,
    auto_historical: bool = False,
) -> dict:
    from app.tasks.jobs import scrape_creator_task

    task = scrape_creator_task.delay(creator_id, mode, auto_historical=auto_historical)
    return {
        "queued": True,
        "task_id": task.id,
        "creator_id": creator_id,
        "mode": mode,
    }


def dispatch_scrape_all(*, auto_historical: bool = True) -> dict:
    from app.tasks.jobs import scrape_all_creators_task

    task = scrape_all_creators_task.delay()
    return {
        "queued": True,
        "task_id": task.id,
        "mode": "daily",
        "auto_historical": auto_historical,
    }


def dispatch_hot_update_coordinator() -> dict:
    from app.tasks.jobs import hot_update_coordinator_task

    task = hot_update_coordinator_task.delay()
    return {"queued": True, "task_id": task.id}
