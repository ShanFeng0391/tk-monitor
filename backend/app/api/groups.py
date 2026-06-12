from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_admin, get_current_user
from app.database import get_db
from app.models import MonitorGroup, MonitoredCreator, User, CollectionSchedule, HotUpdateSegment
from app.schemas import (
    MonitorGroupCreate, MonitorGroupUpdate, MonitorGroupOut, MonitorGroupDeleteConfirm,
    CreatorCreate, CreatorOut, ScrapeResultOut,
    CollectionScheduleOut, CollectionScheduleCreate, CollectionScheduleUpdate,
    HotUpdateSegmentOut, HotUpdateSegmentsReplace,
)
from app.services.collection import collection_service
from app.services.group_helpers import (
    get_active_group,
    ensure_group_has_capacity,
    verify_admin_delete_passwords,
    soft_delete_group,
    purge_expired_groups,
)
from app.services.collection_scheduler import (
    sync_collection_schedules,
    ensure_group_hot_segments,
    replace_group_hot_segments,
)

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


def _group_out(group: MonitorGroup, creator_count: int = 0, schedule_count: int = 0) -> MonitorGroupOut:
    return MonitorGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        historical_view_threshold=group.historical_view_threshold,
        daily_hot_avg_growth_threshold=float(group.daily_hot_avg_growth_threshold or 50.0),
        growth_window_minutes=group.growth_window_minutes,
        scrape_window_hours=group.scrape_window_hours,
        max_creators=group.max_creators,
        is_active=group.is_active,
        creator_count=creator_count,
        schedule_count=schedule_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


async def _group_counts(db: AsyncSession, group_id: int) -> tuple[int, int]:
    creator_count = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.group_id == group_id)
    )).scalar() or 0
    schedule_count = (await db.execute(
        select(func.count(CollectionSchedule.id)).where(CollectionSchedule.group_id == group_id)
    )).scalar() or 0
    return creator_count, schedule_count


def _schedule_out(row: CollectionSchedule) -> CollectionScheduleOut:
    return CollectionScheduleOut.model_validate(row)


def _visible_group_clause():
    return and_(MonitorGroup.is_active == True, MonitorGroup.deleted_at.is_(None))


@router.get("", response_model=list[MonitorGroupOut])
async def list_groups(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await purge_expired_groups(db)
    groups = (await db.execute(
        select(MonitorGroup).where(_visible_group_clause()).order_by(MonitorGroup.created_at.desc())
    )).scalars().all()
    out = []
    for g in groups:
        creator_count, schedule_count = await _group_counts(db, g.id)
        out.append(_group_out(g, creator_count, schedule_count))
    return out


@router.post("", response_model=MonitorGroupOut, status_code=201)
async def create_group(
    data: MonitorGroupCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    group = MonitorGroup(owner_id=admin.id, **data.model_dump())
    db.add(group)
    await db.flush()
    await ensure_group_hot_segments(db, group)
    await db.commit()
    await db.refresh(group)
    return _group_out(group, 0, 0)


@router.get("/{group_id}", response_model=MonitorGroupOut)
async def get_group(
    group_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(
        select(MonitorGroup).where(and_(MonitorGroup.id == group_id, _visible_group_clause()))
    )).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    creator_count, schedule_count = await _group_counts(db, group.id)
    return _group_out(group, creator_count, schedule_count)


@router.put("/{group_id}", response_model=MonitorGroupOut)
async def update_group(
    group_id: int,
    data: MonitorGroupUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    group = (await db.execute(
        select(MonitorGroup).where(
            and_(
                MonitorGroup.id == group_id,
                MonitorGroup.owner_id == admin.id,
                MonitorGroup.deleted_at.is_(None),
            )
        )
    )).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    await db.flush()
    creator_count, schedule_count = await _group_counts(db, group.id)
    return _group_out(group, creator_count, schedule_count)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: int,
    data: MonitorGroupDeleteConfirm,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    verify_admin_delete_passwords(admin, data.password, data.confirm_password)

    group = (await db.execute(
        select(MonitorGroup).where(
            and_(
                MonitorGroup.id == group_id,
                MonitorGroup.owner_id == admin.id,
                MonitorGroup.deleted_at.is_(None),
            )
        )
    )).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    await soft_delete_group(db, group)
    await db.flush()

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)


@router.get("/{group_id}/creators", response_model=list[CreatorOut])
async def list_group_creators(
    group_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    creators = (await db.execute(
        select(MonitoredCreator).where(MonitoredCreator.group_id == group_id)
    )).scalars().all()
    from app.api.helpers import creator_to_out
    return [await creator_to_out(db, c, user) for c in creators]


@router.post("/{group_id}/creators", response_model=CreatorOut, status_code=201)
async def add_group_creator(
    group_id: int,
    data: CreatorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await get_active_group(db, group_id)
    await ensure_group_has_capacity(db, group)

    from app.services.creator_input import (
        normalize_creator_username,
        ensure_creator_not_duplicate,
        verify_creator_with_proxy,
    )

    username = normalize_creator_username(data.tiktok_username)
    creator_info = await verify_creator_with_proxy(db, data.tiktok_username)
    if not creator_info.exists:
        raise HTTPException(status_code=404, detail="TikTok creator not found")

    canonical = (creator_info.username or username).lower()
    await ensure_creator_not_duplicate(db, canonical, tiktok_user_id=creator_info.user_id)

    creator = MonitoredCreator(
        user_id=user.id,
        group_id=group_id,
        tiktok_username=creator_info.username or username,
        tiktok_user_id=creator_info.user_id,
        display_name=creator_info.display_name,
        follower_count=creator_info.follower_count or 0,
    )
    db.add(creator)
    await db.flush()
    from app.api.helpers import creator_to_out
    return await creator_to_out(db, creator, user)


@router.delete("/{group_id}/creators/{creator_id}", status_code=204)
async def remove_group_creator(
    group_id: int,
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.creator_permissions import get_manageable_creator

    await get_active_group(db, group_id)
    creator = await get_manageable_creator(db, creator_id, user)
    if creator.group_id != group_id:
        raise HTTPException(status_code=404, detail="Creator not found")
    await db.delete(creator)


@router.post("/{group_id}/creators/{creator_id}/scrape/historical", response_model=ScrapeResultOut)
async def scrape_group_creator_historical(
    group_id: int,
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.creator_permissions import get_manageable_creator

    await get_active_group(db, group_id)
    creator = await get_manageable_creator(db, creator_id, user)
    if creator.group_id != group_id:
        raise HTTPException(status_code=404, detail="Creator not found")

    from app.services.task_dispatch import dispatch_scrape_creator, use_worker_pool

    if use_worker_pool():
        queued = dispatch_scrape_creator(creator_id, "historical")
        return ScrapeResultOut(message=f"历史采集已加入 Worker 队列（task={queued['task_id']}）")

    stats = await collection_service.scrape_creator(db, creator, mode="historical")
    data = stats.to_dict()
    return ScrapeResultOut(
        message=f"数据采集完成：新增 {data['new_videos']} 条，跳过已采集 {data['skipped_videos']} 条",
        **data,
    )


@router.get("/{group_id}/schedules", response_model=list[CollectionScheduleOut])
async def list_group_schedules(
    group_id: int,
    task_type: str = "daily",
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    result = await db.execute(
        select(CollectionSchedule)
        .where(
            CollectionSchedule.group_id == group_id,
            CollectionSchedule.task_type == task_type,
        )
        .order_by(CollectionSchedule.created_at.desc())
    )
    return [_schedule_out(row) for row in result.scalars().all()]


@router.post("/{group_id}/schedules", response_model=CollectionScheduleOut, status_code=201)
async def create_group_schedule(
    group_id: int,
    data: CollectionScheduleCreate,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    if data.task_type == "hot_ingest" and data.schedule_type != "daily" and data.schedule_type != "once":
        raise HTTPException(status_code=400, detail="热门入库闹钟仅支持 daily / once")
    if (data.task_type or "daily") == "daily" and data.schedule_type == "daily" and not data.run_time:
        raise HTTPException(status_code=400, detail="每日任务需填写 run_time (HH:MM)")
    if data.schedule_type == "once" and not data.run_at:
        raise HTTPException(status_code=400, detail="单次任务需填写 run_at")

    row = CollectionSchedule(
        group_id=group_id,
        name=data.name or "",
        task_type=data.task_type or "daily",
        schedule_type=data.schedule_type,
        run_time=data.run_time,
        run_at=data.run_at,
        timezone=data.timezone or "Asia/Shanghai",
        enabled=data.enabled,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)

    return _schedule_out(row)


@router.put("/{group_id}/schedules/{schedule_id}", response_model=CollectionScheduleOut)
async def update_group_schedule(
    group_id: int,
    schedule_id: int,
    data: CollectionScheduleUpdate,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    row = (await db.execute(
        select(CollectionSchedule).where(
            CollectionSchedule.id == schedule_id,
            CollectionSchedule.group_id == group_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)

    return _schedule_out(row)


@router.delete("/{group_id}/schedules/{schedule_id}", status_code=204)
async def delete_group_schedule(
    group_id: int,
    schedule_id: int,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    row = (await db.execute(
        select(CollectionSchedule).where(
            CollectionSchedule.id == schedule_id,
            CollectionSchedule.group_id == group_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(row)
    await db.commit()

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)


@router.get("/{group_id}/hot-update-segments", response_model=list[HotUpdateSegmentOut])
async def list_hot_update_segments(
    group_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    group = await get_active_group(db, group_id)
    await ensure_group_hot_segments(db, group)
    await db.commit()
    rows = (await db.execute(
        select(HotUpdateSegment)
        .where(HotUpdateSegment.group_id == group_id)
        .order_by(HotUpdateSegment.sort_order.asc())
    )).scalars().all()
    return [HotUpdateSegmentOut.model_validate(r) for r in rows]


@router.put("/{group_id}/hot-update-segments", response_model=list[HotUpdateSegmentOut])
async def save_hot_update_segments(
    group_id: int,
    data: HotUpdateSegmentsReplace,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await get_active_group(db, group_id)
    segments = [s.model_dump() for s in data.segments]
    rows = await replace_group_hot_segments(db, group_id, segments)
    await db.commit()
    return [HotUpdateSegmentOut.model_validate(r) for r in rows]


@router.post("/{group_id}/hot-update/trigger")
async def trigger_group_hot_update(
    group_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.config import get_settings
    from app.services.hot_refresh import run_hot_update_for_group

    settings = get_settings()
    await get_active_group(db, group_id)
    if not settings.local_mode:
        from app.tasks.jobs import hot_update_group_task

        task = hot_update_group_task.delay(group_id, "manual")
        return {"message": "热门更新已加入队列", "task_id": task.id, "group_id": group_id}
    result = await run_hot_update_for_group(db, group_id, trigger="manual")
    return {"message": "热门更新已完成", "result": result}


@router.post("/{group_id}/hot-ingest/trigger")
async def trigger_group_hot_ingest(
    group_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.config import get_settings
    from app.services.hot_refresh import run_hot_ingest_for_group

    settings = get_settings()
    await get_active_group(db, group_id)
    if not settings.local_mode:
        from app.tasks.jobs import hot_ingest_group_task

        task = hot_ingest_group_task.delay(group_id, "manual")
        return {"message": "热门入库已加入队列", "task_id": task.id, "group_id": group_id}
    result = await run_hot_ingest_for_group(db, group_id, trigger="manual")
    return {"message": "热门入库已完成", "result": result}
