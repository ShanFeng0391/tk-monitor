"""video_snapshots 归档：删除超过保留期的快照，避免表无限膨胀。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import VideoSnapshot

logger = logging.getLogger(__name__)
settings = get_settings()


async def count_snapshots_before(db: AsyncSession, cutoff: datetime) -> int:
    result = await db.execute(
        select(func.count(VideoSnapshot.id)).where(VideoSnapshot.snapshot_at < cutoff)
    )
    return int(result.scalar() or 0)


async def purge_old_video_snapshots(
    db: AsyncSession,
    *,
    retention_days: int | None = None,
    batch_size: int | None = None,
) -> dict:
    days = retention_days if retention_days is not None else settings.snapshot_retention_days
    batch = batch_size if batch_size is not None else settings.snapshot_purge_batch_size
    cutoff = datetime.utcnow() - timedelta(days=max(days, 1))

    total_deleted = 0
    batches = 0

    while True:
        id_rows = (
            await db.execute(
                select(VideoSnapshot.id)
                .where(VideoSnapshot.snapshot_at < cutoff)
                .order_by(VideoSnapshot.id.asc())
                .limit(batch)
            )
        ).scalars().all()
        if not id_rows:
            break

        result = await db.execute(delete(VideoSnapshot).where(VideoSnapshot.id.in_(id_rows)))
        deleted = int(result.rowcount or 0)
        total_deleted += deleted
        batches += 1
        await db.commit()

        if deleted < batch:
            break

    logger.info(
        "snapshot purge done: deleted=%s batches=%s cutoff=%s retention_days=%s",
        total_deleted,
        batches,
        cutoff.isoformat(),
        days,
    )
    return {
        "deleted": total_deleted,
        "batches": batches,
        "cutoff": cutoff.isoformat(),
        "retention_days": days,
    }
