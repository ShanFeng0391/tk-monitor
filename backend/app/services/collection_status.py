"""采集任务状态（Dashboard / 运维）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CollectionSchedule, MonitorGroup, MonitoredCreator
from app.services.hot_refresh import is_hot_update_running
from app.services.hot_segment_utils import beijing_now, current_segment


async def build_collection_status(
    db: AsyncSession,
    *,
    group_id: Optional[int] = None,
) -> dict:
    query = (
        select(MonitorGroup)
        .options(selectinload(MonitorGroup.hot_update_segments))
        .where(MonitorGroup.is_active == True, MonitorGroup.deleted_at.is_(None))
        .order_by(MonitorGroup.id.asc())
    )
    if group_id is not None:
        query = query.where(MonitorGroup.id == group_id)

    groups = (await db.execute(query)).scalars().all()
    now = datetime.utcnow()
    items = []

    for group in groups:
        segments = [
            {
                "start_time": s.start_time,
                "end_time": s.end_time,
                "interval_minutes": s.interval_minutes,
            }
            for s in sorted(group.hot_update_segments, key=lambda x: x.sort_order)
        ]
        seg = current_segment(segments, beijing_now()) if segments else None
        interval_min = int(seg["interval_minutes"]) if seg else None
        next_hot_update_at = None
        if group.last_hot_update_at and interval_min:
            next_hot_update_at = group.last_hot_update_at + timedelta(minutes=max(interval_min, 5))

        last_hot_ingest_at = (await db.execute(
            select(func.max(MonitoredCreator.last_hot_ingest_at)).where(
                MonitoredCreator.group_id == group.id,
                MonitoredCreator.is_active == True,
            )
        )).scalar()

        daily_enabled = (await db.execute(
            select(func.count(CollectionSchedule.id)).where(
                CollectionSchedule.group_id == group.id,
                CollectionSchedule.task_type == "daily",
                CollectionSchedule.enabled == True,
            )
        )).scalar() or 0

        hot_ingest_enabled = (await db.execute(
            select(func.count(CollectionSchedule.id)).where(
                CollectionSchedule.group_id == group.id,
                CollectionSchedule.task_type == "hot_ingest",
                CollectionSchedule.enabled == True,
            )
        )).scalar() or 0

        items.append({
            "group_id": group.id,
            "group_name": group.name,
            "last_hot_update_at": group.last_hot_update_at,
            "last_hot_ingest_at": last_hot_ingest_at,
            "hot_update_running": is_hot_update_running(group.id),
            "current_segment": (
                {
                    "start_time": seg["start_time"],
                    "end_time": seg["end_time"],
                    "interval_minutes": seg["interval_minutes"],
                }
                if seg
                else None
            ),
            "next_hot_update_at": next_hot_update_at,
            "b_due_now": bool(
                seg
                and (not group.last_hot_update_at or (now - group.last_hot_update_at).total_seconds()
                     >= max(interval_min or 5, 5) * 60)
            ),
            "daily_schedules_enabled": daily_enabled,
            "hot_ingest_schedules_enabled": hot_ingest_enabled,
            "segment_count": len(segments),
        })

    return {
        "items": items,
        "coordinator": {
            "status": "scheduled",
            "check_interval_minutes": 1,
            "description": "每分钟检查各分组 B 线是否到期",
        },
    }
