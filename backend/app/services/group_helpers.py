from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import (
    MonitorGroup, MonitoredCreator, User, CollectionSchedule,
    Video, HistoricalViralArchive, DailyHotRecord, VideoDramaRecognition, DramaStats,
)
from app.services.drama_names import is_invalid_drama_name

GROUP_RETENTION_DAYS = 7


def group_visible(group: MonitorGroup) -> bool:
    return group.deleted_at is None and group.is_active


async def purge_expired_groups(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(days=GROUP_RETENTION_DAYS)
    result = await db.execute(
        select(MonitorGroup).where(
            MonitorGroup.deleted_at.isnot(None),
            MonitorGroup.deleted_at < cutoff,
        )
    )
    groups = result.scalars().all()
    for group in groups:
        schedules = (await db.execute(
            select(CollectionSchedule).where(CollectionSchedule.group_id == group.id)
        )).scalars().all()
        for schedule in schedules:
            await db.delete(schedule)
        await db.execute(
            update(MonitoredCreator)
            .where(MonitoredCreator.group_id == group.id)
            .values(group_id=None)
        )
        await db.delete(group)
    return len(groups)


async def get_active_group(db: AsyncSession, group_id: int) -> MonitorGroup:
    group = (await db.execute(
        select(MonitorGroup).where(
            MonitorGroup.id == group_id,
            MonitorGroup.is_active == True,
            MonitorGroup.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="博主类别不存在或已停用")
    return group


async def ensure_group_has_capacity(db: AsyncSession, group: MonitorGroup) -> None:
    from sqlalchemy import func

    cnt = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.group_id == group.id)
    )).scalar() or 0
    if cnt >= group.max_creators:
        raise HTTPException(status_code=400, detail=f"该类别博主已达上限 ({group.max_creators})")


def verify_admin_delete_passwords(admin: User, password: str, confirm_password: str) -> None:
    if not password.strip() or not confirm_password.strip():
        raise HTTPException(status_code=400, detail="请输入管理员密码")
    if not verify_password(password, admin.password_hash):
        raise HTTPException(status_code=403, detail="第一次密码验证失败")
    if not verify_password(confirm_password, admin.password_hash):
        raise HTTPException(status_code=403, detail="第二次密码验证失败")


async def soft_delete_group(db: AsyncSession, group: MonitorGroup) -> None:
    group.deleted_at = datetime.utcnow()
    group.is_active = False
    schedules = (await db.execute(
        select(CollectionSchedule).where(CollectionSchedule.group_id == group.id)
    )).scalars().all()
    for schedule in schedules:
        schedule.enabled = False


def video_in_group(group_id: int):
    return Video.creator.has(MonitoredCreator.group_id == group_id)


def archive_in_group(group_id: int):
    return HistoricalViralArchive.video.has(video_in_group(group_id))


def daily_hot_in_group(group_id: int):
    return DailyHotRecord.video.has(video_in_group(group_id))


async def list_dramas_for_group(
    db: AsyncSession,
    group_id: Optional[int] = None,
    *,
    trending: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    if group_id is None:
        query = select(DramaStats).order_by(DramaStats.total_views.desc())
        if trending:
            query = query.where(DramaStats.trend_direction.in_(["rising", "stable"])).limit(limit or 20)
        rows = (await db.execute(query)).scalars().all()
        return [{
            "drama_name": row.drama_name,
            "drama_type": row.drama_type,
            "total_videos": row.total_videos,
            "total_views": row.total_views,
            "total_likes": row.total_likes,
            "viral_videos": row.viral_videos,
            "trend_direction": row.trend_direction or "stable",
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
        } for row in rows]

    query = (
        select(
            VideoDramaRecognition.drama_name,
            func.max(VideoDramaRecognition.drama_type).label("drama_type"),
            func.count(Video.id).label("total_videos"),
            func.coalesce(func.sum(Video.view_count), 0).label("total_views"),
            func.coalesce(func.sum(Video.like_count), 0).label("total_likes"),
            func.coalesce(
                func.sum(case((Video.is_historical_viral == True, 1), else_=0)),  # noqa: E712
                0,
            ).label("viral_videos"),
            func.min(VideoDramaRecognition.completed_at).label("first_seen_at"),
            func.max(VideoDramaRecognition.completed_at).label("last_seen_at"),
        )
        .join(Video, Video.id == VideoDramaRecognition.video_id)
        .join(MonitoredCreator, MonitoredCreator.id == Video.creator_id)
        .where(
            MonitoredCreator.group_id == group_id,
            VideoDramaRecognition.status == "success",
            VideoDramaRecognition.drama_name.isnot(None),
            VideoDramaRecognition.drama_name.notin_(["未知", "非影视内容"]),
        )
        .group_by(VideoDramaRecognition.drama_name)
        .order_by(func.coalesce(func.sum(Video.view_count), 0).desc())
    )
    if limit:
        query = query.limit(limit)
    rows = (await db.execute(query)).all()
    out = []
    for row in rows:
        if is_invalid_drama_name(row.drama_name):
            continue
        out.append({
            "drama_name": row.drama_name,
            "drama_type": row.drama_type,
            "total_videos": int(row.total_videos or 0),
            "total_views": int(row.total_views or 0),
            "total_likes": int(row.total_likes or 0),
            "viral_videos": int(row.viral_videos or 0),
            "trend_direction": "stable",
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
        })
    return out
