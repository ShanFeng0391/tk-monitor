"""影视剧聚合统计：按 recognition 表实际关联视频数重算，避免累加计数失真。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DramaStats, Video, VideoDramaRecognition
from app.services.drama_names import is_invalid_drama_name

_INVALID_DRAMA_NAMES = frozenset({"未知", "非影视内容"})


def _is_countable_drama(name: str | None) -> bool:
    if not name or name in _INVALID_DRAMA_NAMES:
        return False
    return not is_invalid_drama_name(name)


async def rebuild_drama_stats_for(db: AsyncSession, drama_name: str) -> None:
    """按当前 recognition 记录重算单个影视剧的关联视频数。"""
    if not _is_countable_drama(drama_name):
        return

    row = (await db.execute(
        select(
            func.count(VideoDramaRecognition.video_id),
            func.coalesce(func.sum(Video.view_count), 0),
            func.coalesce(func.sum(Video.like_count), 0),
            func.coalesce(
                func.sum(case((Video.is_historical_viral == True, 1), else_=0)),  # noqa: E712
                0,
            ),
            func.min(VideoDramaRecognition.completed_at),
            func.max(VideoDramaRecognition.completed_at),
            func.max(VideoDramaRecognition.drama_type),
        )
        .join(Video, Video.id == VideoDramaRecognition.video_id)
        .where(
            VideoDramaRecognition.drama_name == drama_name,
            VideoDramaRecognition.status == "success",
        )
    )).one()

    total_videos = int(row[0] or 0)
    existing = (await db.execute(
        select(DramaStats).where(DramaStats.drama_name == drama_name)
    )).scalar_one_or_none()

    if total_videos == 0:
        if existing:
            await db.delete(existing)
        return

    now = datetime.utcnow()
    if not existing:
        existing = DramaStats(drama_name=drama_name, first_seen_at=row[4] or now)
        db.add(existing)

    existing.total_videos = total_videos
    existing.total_views = int(row[1] or 0)
    existing.total_likes = int(row[2] or 0)
    existing.viral_videos = int(row[3] or 0)
    if row[6] and row[6] != "未知":
        existing.drama_type = row[6]
    if row[4]:
        existing.first_seen_at = row[4]
    existing.last_seen_at = row[5] or now
    existing.updated_at = now


async def rebuild_all_drama_stats(db: AsyncSession) -> int:
    """全量重算 drama_stats，返回有效影视剧数量。"""
    names = (await db.execute(
        select(VideoDramaRecognition.drama_name)
        .where(VideoDramaRecognition.status == "success")
        .distinct()
    )).scalars().all()

    valid_names = sorted({n for n in names if _is_countable_drama(n)})
    await db.execute(delete(DramaStats))
    for name in valid_names:
        await rebuild_drama_stats_for(db, name)
    return len(valid_names)
