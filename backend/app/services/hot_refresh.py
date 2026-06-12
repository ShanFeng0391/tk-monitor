"""当日热门：线 A 入库 + 线 B 更新（分时段周期）。"""
from __future__ import annotations

import logging
from datetime import datetime, date

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Video, DailyHotRecord, MonitoredCreator, MonitorGroup
from app.services.collection import collection_service
from app.services.collection_policy import is_within_hot_window
from app.services.distributed_lock import (
    is_hot_update_running,
    local_hot_update_lock,
    release_hot_update_lock,
    try_acquire_hot_update_lock,
)
from app.services.thresholds import thresholds_from_group, get_default_thresholds
from app.services.video_classifier import (
    calc_avg_view_velocity,
    check_daily_hot,
    apply_video_classification,
    resolve_video_category,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _threshold_for_video(video: Video):
    creator = video.creator
    if creator and creator.group:
        return thresholds_from_group(creator.group)
    if creator and creator.collection:
        from app.services.thresholds import thresholds_from_collection
        return thresholds_from_collection(creator.collection)
    return get_default_thresholds()


async def reconcile_daily_hot_records(db: AsyncSession, group_id: int | None = None) -> int:
    """取消不再符合热门条件的标记，并删除当日热门记录。"""
    today = date.today()
    query = (
        select(Video)
        .options(
            selectinload(Video.creator).selectinload(MonitoredCreator.group),
            selectinload(Video.creator).selectinload(MonitoredCreator.collection),
        )
        .where(Video.is_daily_hot == True)
    )
    if group_id is not None:
        query = query.where(Video.creator.has(MonitoredCreator.group_id == group_id))

    result = await db.execute(query)
    removed = 0

    for video in result.scalars().all():
        threshold = _threshold_for_video(video)
        avg = calc_avg_view_velocity(video.view_count or 0, video.published_at)
        if check_daily_hot(avg, threshold, video.published_at):
            continue

        video.is_daily_hot = False
        video.daily_hot_at = None
        video.category = resolve_video_category(video)

        await db.execute(
            delete(DailyHotRecord).where(
                and_(DailyHotRecord.video_id == video.id, DailyHotRecord.hot_date == today)
            )
        )
        removed += 1

    return removed


async def reclassify_group_daily_hot(db: AsyncSession, group_id: int) -> int:
    """线 B：对分组热门窗口内全部视频重算分类（新增/保留/取消当日热门）。"""
    group = (
        await db.execute(select(MonitorGroup).where(MonitorGroup.id == group_id))
    ).scalar_one_or_none()
    if not group:
        return 0

    threshold = thresholds_from_group(group)
    window = threshold.scrape_window_hours
    now = datetime.utcnow()

    result = await db.execute(
        select(Video)
        .join(MonitoredCreator, Video.creator_id == MonitoredCreator.id)
        .where(MonitoredCreator.group_id == group_id, MonitoredCreator.is_active == True)
    )
    count = 0
    for video in result.scalars().all():
        if not is_within_hot_window(video.published_at, window, now):
            continue
        creator = (
            await db.execute(
                select(MonitoredCreator).where(MonitoredCreator.id == video.creator_id)
            )
        ).scalar_one_or_none()
        username = creator.tiktok_username if creator else ""
        await apply_video_classification(
            db,
            video,
            threshold,
            username,
            scrape_interval_minutes=threshold.growth_window_minutes,
        )
        count += 1
    return count


async def _run_hot_update_body(db: AsyncSession, group_id: int, trigger: str) -> dict:
    stats = await collection_service.scrape_group_creators(db, group_id, mode="hot_update")
    reclassified = await reclassify_group_daily_hot(db, group_id)
    removed = await reconcile_daily_hot_records(db, group_id=group_id)

    group = (
        await db.execute(select(MonitorGroup).where(MonitorGroup.id == group_id))
    ).scalar_one_or_none()
    if group:
        group.last_hot_update_at = datetime.utcnow()

    await db.commit()
    return {
        **stats,
        "group_id": group_id,
        "reclassified": reclassified,
        "removed_hot": removed,
        "trigger": trigger,
        "skipped": False,
    }


async def run_hot_update_for_group(
    db: AsyncSession,
    group_id: int,
    *,
    trigger: str = "scheduled",
) -> dict:
    """线 B：更新已有视频播放 + 重判热门 + 清理不达标（同组运行中则 skip）。"""
    if is_hot_update_running(group_id):
        logger.info("hot_update group=%s skipped (%s): already running", group_id, trigger)
        return {"group_id": group_id, "skipped": True, "reason": "running", "trigger": trigger}

    if settings.local_mode:
        async with local_hot_update_lock(group_id):
            return await _run_hot_update_body(db, group_id, trigger)

    if not try_acquire_hot_update_lock(group_id):
        return {"group_id": group_id, "skipped": True, "reason": "running", "trigger": trigger}
    try:
        return await _run_hot_update_body(db, group_id, trigger)
    finally:
        release_hot_update_lock(group_id)


async def run_hot_ingest_for_group(db: AsyncSession, group_id: int, *, trigger: str = "schedule") -> dict:
    """线 A：热门窗口内新视频入库，完成后自动串联一次线 B（B 运行中则 skip）。"""
    stats = await collection_service.scrape_group_creators(db, group_id, mode="hot_ingest")
    await db.commit()

    chain = await run_hot_update_for_group(db, group_id, trigger=f"ingest_chain:{trigger}")
    return {
        "ingest": stats,
        "update_chain": chain,
        "group_id": group_id,
        "trigger": trigger,
    }


async def run_hot_update_all_due_groups(db: AsyncSession, *, dispatch_only: bool = False) -> list[dict]:
    """协调器：对所有配置了分时段的分组执行到期的线 B（由调度器按间隔触发）。"""
    from app.services.hot_segment_utils import current_segment, beijing_now

    groups = (await db.execute(
        select(MonitorGroup)
        .options(selectinload(MonitorGroup.hot_update_segments))
        .where(MonitorGroup.is_active == True, MonitorGroup.deleted_at.is_(None))
    )).scalars().all()

    results = []
    now = datetime.utcnow()
    use_dispatch = dispatch_only or not settings.local_mode
    for group in groups:
        segments = [
            {
                "start_time": s.start_time,
                "end_time": s.end_time,
                "interval_minutes": s.interval_minutes,
            }
            for s in sorted(group.hot_update_segments, key=lambda x: x.sort_order)
        ]
        if not segments:
            continue
        seg = current_segment(segments, beijing_now())
        if not seg:
            continue
        interval_sec = max(int(seg["interval_minutes"]), 5) * 60
        last = group.last_hot_update_at
        if last and (now - last).total_seconds() < interval_sec:
            continue
        try:
            if use_dispatch:
                from app.tasks.jobs import hot_update_group_task

                hot_update_group_task.delay(group.id, "scheduled")
                results.append({"group_id": group.id, "dispatched": True, "trigger": "scheduled"})
            else:
                result = await run_hot_update_for_group(db, group.id, trigger="scheduled")
                results.append(result)
        except Exception:
            await db.rollback()
            logger.exception("hot_update failed for group %s", group.id)
            raise
    return results


# 兼容旧入口
async def refresh_daily_hot_market(db: AsyncSession) -> dict:
    results = await run_hot_update_all_due_groups(db)
    return {"groups": results, "count": len(results)}
