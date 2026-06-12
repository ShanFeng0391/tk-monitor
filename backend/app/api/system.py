from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import get_current_admin
from app.database import async_session, get_db
from app.models import User, CollectionSchedule
from app.schemas import (
    SystemHealth,
    SystemSettingsOut,
    SystemSettingsUpdate,
    CollectionScheduleOut,
    CollectionScheduleCreate,
    CollectionScheduleUpdate,
)
from app.services.runtime_settings import runtime
from app.services.collection import collection_service
from app.services.hot_refresh import run_hot_update_all_due_groups, run_hot_ingest_for_group, run_hot_update_for_group
from app.services.collection_scheduler import sync_collection_schedules

router = APIRouter(prefix="/api/v1/system")
settings = get_settings()


def _schedule_out(row: CollectionSchedule) -> CollectionScheduleOut:
    return CollectionScheduleOut.model_validate(row)


@router.get("/health", response_model=SystemHealth)
async def health_check():
    db_status = "ok"
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    if settings.local_mode:
        redis_status = "skipped"
        celery_status = "skipped"
        overall = "healthy" if db_status == "ok" else "degraded"
    else:
        redis_status = "ok"
        celery_status = "unknown"
        try:
            import redis

            r = redis.from_url(settings.redis_url)
            r.ping()
        except Exception:
            redis_status = "error"
        try:
            from app.tasks.celery_app import celery_app

            replies = celery_app.control.inspect(timeout=2.0).ping()
            celery_status = "ok" if replies else "no_workers"
        except Exception:
            celery_status = "error"
        overall = (
            "healthy"
            if db_status == "ok" and redis_status == "ok" and celery_status == "ok"
            else "degraded"
        )

    return SystemHealth(
        status=overall,
        database=db_status,
        redis=redis_status,
        celery=celery_status,
        timestamp=datetime.utcnow(),
    )


@router.get("/settings", response_model=SystemSettingsOut)
async def get_system_settings(_admin: User = Depends(get_current_admin)):
    return SystemSettingsOut(**runtime.to_api_dict())


@router.put("/settings", response_model=SystemSettingsOut)
async def update_system_settings(
    data: SystemSettingsUpdate,
    request: Request,
    _admin: User = Depends(get_current_admin),
):
    async with async_session() as db:
        saved = await runtime.save(db, data.model_dump(exclude_unset=True))

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None and data.growth_window is not None:
        pass  # B 线分时段周期在分组配置，growth_window 仅作默认间隔参考

    return SystemSettingsOut(**saved)


@router.get("/collection-schedules", response_model=list[CollectionScheduleOut])
async def list_collection_schedules(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectionSchedule).order_by(CollectionSchedule.created_at.desc())
    )
    return [_schedule_out(row) for row in result.scalars().all()]


@router.post("/collection-schedules", response_model=CollectionScheduleOut, status_code=201)
async def create_collection_schedule(
    data: CollectionScheduleCreate,
    request: Request,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if data.schedule_type == "daily" and not data.run_time:
        raise HTTPException(status_code=400, detail="每日任务需填写 run_time (HH:MM)")
    if data.schedule_type == "once" and not data.run_at:
        raise HTTPException(status_code=400, detail="单次任务需填写 run_at")

    row = CollectionSchedule(
        name=data.name or "",
        schedule_type=data.schedule_type,
        task_type="daily",
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


@router.put("/collection-schedules/{schedule_id}", response_model=CollectionScheduleOut)
async def update_collection_schedule(
    schedule_id: int,
    data: CollectionScheduleUpdate,
    request: Request,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if row.schedule_type == "once" and row.executed:
        raise HTTPException(status_code=400, detail="已执行的单次任务不可修改")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)

    return _schedule_out(row)


@router.delete("/collection-schedules/{schedule_id}", status_code=204)
async def delete_collection_schedule(
    schedule_id: int,
    request: Request,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(row)
    await db.commit()

    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        await sync_collection_schedules(scheduler, db)


@router.get("/tasks")
async def task_status(request: Request, _admin: User = Depends(get_current_admin)):
    scheduler = getattr(request.app.state, "scheduler", None)
    coordinator_next = None
    if scheduler:
        job = scheduler.get_job("hot_update_coordinator")
        if job and job.next_run_time:
            coordinator_next = job.next_run_time.isoformat()

    async with async_session() as db:
        from app.services.collection_status import build_collection_status

        status = await build_collection_status(db)

    return {
        "tasks": [
            {
                "id": "hot_update_coordinator",
                "name": "热门更新 B 线（分时段周期）",
                "status": "scheduled",
                "next_run_at": coordinator_next,
            },
            {
                "id": "creator_scrape",
                "name": "博主 Daily 增量采集闹钟",
                "status": "scheduled",
            },
            {
                "id": "hot_ingest",
                "name": "热门入库 A 线闹钟（按分组）",
                "status": "scheduled",
            },
        ],
        "groups": status["items"],
        "coordinator": status["coordinator"],
    }


@router.post("/tasks/{task_id}/trigger")
async def trigger_task(task_id: str, _admin: User = Depends(get_current_admin)):
    from app.services.task_dispatch import (
        dispatch_hot_update_coordinator,
        dispatch_scrape_all,
        use_worker_pool,
    )

    if task_id in ("hot_refresh", "hot_update_coordinator"):
        if use_worker_pool():
            result = dispatch_hot_update_coordinator()
            return {"message": "热门更新协调任务已加入队列", "task_id": task_id, "result": result}
        async with async_session() as db:
            result = await run_hot_update_all_due_groups(db)
        return {"message": "热门更新协调任务已执行", "task_id": task_id, "result": result}

    if task_id == "scrape_all":
        if use_worker_pool():
            result = dispatch_scrape_all()
            return {"message": "全库采集已加入 Worker 队列", "task_id": task_id, "result": result}
        async with async_session() as db:
            result = await collection_service.scrape_all_creators(db, mode="daily")
            await db.commit()
        return {"message": "博主增量采集已完成", "task_id": task_id, "result": result}

    return {"message": "Unknown task", "task_id": task_id}
