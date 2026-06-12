"""采集闹钟（daily / hot_ingest）与热门更新 B 线协调调度。"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import async_session
from app.models import CollectionSchedule, MonitorGroup, HotUpdateSegment
from app.services.collection import collection_service
from app.services.hot_refresh import run_hot_ingest_for_group, run_hot_update_all_due_groups
from app.services.hot_segment_utils import default_segments_for_group, validate_segments_cover_24h

logger = logging.getLogger(__name__)
settings = get_settings()

HOT_UPDATE_COORDINATOR_ID = "hot_update_coordinator"
SNAPSHOT_PURGE_JOB_ID = "snapshot_purge"
POSTGRES_BACKUP_JOB_ID = "postgres_backup"
CREATOR_JOB_PREFIX = "creator_scrape_"
HOT_INGEST_JOB_PREFIX = "hot_ingest_"
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _creator_job_id(schedule_id: int) -> str:
    return f"{CREATOR_JOB_PREFIX}{schedule_id}"


def _hot_ingest_job_id(schedule_id: int) -> str:
    return f"{HOT_INGEST_JOB_PREFIX}{schedule_id}"


def _parse_run_time(run_time: str) -> tuple[int, int]:
    match = TIME_PATTERN.match((run_time or "").strip())
    if not match:
        raise ValueError("run_time 格式应为 HH:MM")
    return int(match.group(1)), int(match.group(2))


async def _run_creator_scrape(schedule_id: int) -> None:
    if not settings.local_mode:
        from app.tasks.jobs import daily_schedule_task

        daily_schedule_task.delay(schedule_id)
        return

    async with async_session() as db:
        result = await db.execute(
            select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if not schedule or not schedule.enabled:
            return
        if (schedule.task_type or "daily") != "daily":
            return
        if schedule.schedule_type == "once" and schedule.executed:
            return

        try:
            if schedule.group_id:
                await collection_service.scrape_group_creators(
                    db, schedule.group_id, mode="daily", auto_historical=True,
                )
            else:
                await collection_service.scrape_all_creators(db, mode="daily", auto_historical=True)
            schedule.last_run_at = datetime.utcnow()
            if schedule.schedule_type == "once":
                schedule.executed = True
                schedule.enabled = False
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Creator scrape schedule %s failed", schedule_id)
            raise


async def _run_hot_ingest_schedule(schedule_id: int) -> None:
    if not settings.local_mode:
        async with async_session() as db:
            result = await db.execute(
                select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            if not schedule or not schedule.enabled or schedule.task_type != "hot_ingest":
                return
            if not schedule.group_id:
                return
            if schedule.schedule_type == "once" and schedule.executed:
                return
            from app.tasks.jobs import hot_ingest_group_task

            hot_ingest_group_task.delay(schedule.group_id, "schedule", schedule_id)
        return

    async with async_session() as db:
        result = await db.execute(
            select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if not schedule or not schedule.enabled:
            return
        if schedule.task_type != "hot_ingest":
            return
        if not schedule.group_id:
            logger.warning("hot_ingest schedule %s missing group_id", schedule_id)
            return
        if schedule.schedule_type == "once" and schedule.executed:
            return

        try:
            await run_hot_ingest_for_group(db, schedule.group_id, trigger="schedule")
            schedule.last_run_at = datetime.utcnow()
            if schedule.schedule_type == "once":
                schedule.executed = True
                schedule.enabled = False
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Hot ingest schedule %s failed", schedule_id)
            raise


async def _hot_update_coordinator_job() -> None:
    if not settings.local_mode:
        from app.tasks.jobs import hot_update_coordinator_task

        hot_update_coordinator_task.delay()
        return

    async with async_session() as db:
        try:
            await run_hot_update_all_due_groups(db)
        except Exception:
            await db.rollback()
            logger.exception("Hot update coordinator failed")
            raise


def _remove_jobs_with_prefix(scheduler: BaseScheduler, prefix: str) -> None:
    for job in scheduler.get_jobs():
        if job.id.startswith(prefix):
            scheduler.remove_job(job.id)


def _register_daily_schedule(scheduler: BaseScheduler, schedule: CollectionSchedule) -> None:
    if (schedule.task_type or "daily") != "daily":
        return
    job_id = _creator_job_id(schedule.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if not schedule.enabled:
        return
    if schedule.schedule_type == "once" and schedule.executed:
        return

    if schedule.schedule_type == "daily":
        hour, minute = _parse_run_time(schedule.run_time or "09:00")
        tz = ZoneInfo(schedule.timezone or "Asia/Shanghai")
        scheduler.add_job(
            _run_creator_scrape,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=job_id,
            args=[schedule.id],
            replace_existing=True,
        )
        return

    if schedule.schedule_type == "once":
        run_at = schedule.run_at
        if not run_at:
            return
        trigger = (
            DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=3))
            if run_at <= datetime.utcnow()
            else DateTrigger(run_date=run_at)
        )
        scheduler.add_job(
            _run_creator_scrape,
            trigger,
            id=job_id,
            args=[schedule.id],
            replace_existing=True,
        )


def _register_hot_ingest_schedule(scheduler: BaseScheduler, schedule: CollectionSchedule) -> None:
    if schedule.task_type != "hot_ingest":
        return
    job_id = _hot_ingest_job_id(schedule.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if not schedule.enabled or not schedule.group_id:
        return
    if schedule.schedule_type == "once" and schedule.executed:
        return

    if schedule.schedule_type == "daily":
        hour, minute = _parse_run_time(schedule.run_time or "09:00")
        tz = ZoneInfo(schedule.timezone or "Asia/Shanghai")
        scheduler.add_job(
            _run_hot_ingest_schedule,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=job_id,
            args=[schedule.id],
            replace_existing=True,
        )
        return

    if schedule.schedule_type == "once":
        run_at = schedule.run_at
        if not run_at:
            return
        trigger = (
            DateTrigger(run_date=datetime.utcnow() + timedelta(seconds=3))
            if run_at <= datetime.utcnow()
            else DateTrigger(run_date=run_at)
        )
        scheduler.add_job(
            _run_hot_ingest_schedule,
            trigger,
            id=job_id,
            args=[schedule.id],
            replace_existing=True,
        )


async def ensure_group_hot_segments(db: AsyncSession, group: MonitorGroup) -> None:
    existing = (
        await db.execute(
            select(HotUpdateSegment.id).where(HotUpdateSegment.group_id == group.id).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return
    for item in default_segments_for_group(group.growth_window_minutes or 30):
        db.add(HotUpdateSegment(group_id=group.id, **item))
    await db.flush()


async def sync_collection_schedules(scheduler: BaseScheduler, db: AsyncSession) -> None:
    _remove_jobs_with_prefix(scheduler, CREATOR_JOB_PREFIX)
    _remove_jobs_with_prefix(scheduler, HOT_INGEST_JOB_PREFIX)

    result = await db.execute(
        select(CollectionSchedule).order_by(CollectionSchedule.id.asc())
    )
    for schedule in result.scalars().all():
        try:
            _register_daily_schedule(scheduler, schedule)
            _register_hot_ingest_schedule(scheduler, schedule)
        except Exception:
            logger.exception("Failed to register schedule %s", schedule.id)


def register_hot_update_coordinator(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        _hot_update_coordinator_job,
        IntervalTrigger(minutes=1),
        id=HOT_UPDATE_COORDINATOR_ID,
        replace_existing=True,
    )


async def _snapshot_purge_job() -> None:
    if settings.local_mode:
        async with async_session() as db:
            from app.services.snapshot_archive import purge_old_video_snapshots

            try:
                result = await purge_old_video_snapshots(db)
                logger.info("snapshot purge (local): %s", result)
            except Exception:
                await db.rollback()
                logger.exception("Snapshot purge failed")
        return

    from app.tasks.jobs import purge_video_snapshots_task

    purge_video_snapshots_task.delay()


async def _postgres_backup_job() -> None:
    if settings.local_mode or not settings.postgres_backup_enabled:
        return

    from app.tasks.jobs import postgres_backup_task

    postgres_backup_task.delay()


def register_snapshot_purge_job(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        _snapshot_purge_job,
        CronTrigger(hour=3, minute=30, timezone=ZoneInfo("Asia/Shanghai")),
        id=SNAPSHOT_PURGE_JOB_ID,
        replace_existing=True,
    )


def register_postgres_backup_job(scheduler: BaseScheduler) -> None:
    if settings.local_mode or not settings.postgres_backup_enabled:
        return
    scheduler.add_job(
        _postgres_backup_job,
        CronTrigger(hour=4, minute=0, timezone=ZoneInfo("Asia/Shanghai")),
        id=POSTGRES_BACKUP_JOB_ID,
        replace_existing=True,
    )


async def sync_hot_segments_for_all_groups(db: AsyncSession) -> None:
    groups = (await db.execute(
        select(MonitorGroup).where(MonitorGroup.deleted_at.is_(None))
    )).scalars().all()
    for group in groups:
        await ensure_group_hot_segments(db, group)
    await db.commit()


async def replace_group_hot_segments(db: AsyncSession, group_id: int, segments: list[dict]) -> list[HotUpdateSegment]:
    validate_segments_cover_24h(segments)
    await db.execute(
        HotUpdateSegment.__table__.delete().where(HotUpdateSegment.group_id == group_id)
    )
    rows = []
    for idx, seg in enumerate(segments):
        row = HotUpdateSegment(
            group_id=group_id,
            start_time=seg["start_time"],
            end_time=seg["end_time"],
            interval_minutes=int(seg["interval_minutes"]),
            sort_order=seg.get("sort_order", idx),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows
