from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import async_session
from app.services.collection_scheduler import (
    sync_collection_schedules,
    register_hot_update_coordinator,
    register_snapshot_purge_job,
    register_postgres_backup_job,
    sync_hot_segments_for_all_groups,
)


async def bootstrap_scheduler(scheduler: AsyncIOScheduler) -> None:
    async with async_session() as db:
        await sync_hot_segments_for_all_groups(db)
        await sync_collection_schedules(scheduler, db)
    register_schedule_resync(scheduler)


def register_schedule_resync(scheduler: AsyncIOScheduler) -> None:
    """混合部署下 Beat 定期重载 DB 闹钟（API 进程不持有 scheduler）。"""

    async def _resync() -> None:
        async with async_session() as db:
            await sync_collection_schedules(scheduler, db)

    scheduler.add_job(
        _resync,
        IntervalTrigger(minutes=2),
        id="schedule_resync",
        replace_existing=True,
    )


def start_scheduler():
    scheduler = AsyncIOScheduler()
    register_hot_update_coordinator(scheduler)
    register_snapshot_purge_job(scheduler)
    register_postgres_backup_job(scheduler)
    scheduler.start()
    return scheduler


def stop_scheduler(scheduler):
    if scheduler:
        scheduler.shutdown(wait=False)
