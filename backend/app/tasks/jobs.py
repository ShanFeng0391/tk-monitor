"""Celery 采集任务（混合部署：Worker 执行重采集）。"""

from __future__ import annotations



import asyncio

import logging

from typing import Optional



from celery import chord



from app.config import get_settings

from app.database import async_session

from app.services.collection import collection_service

from app.tasks.celery_app import celery_app



logger = logging.getLogger(__name__)

settings = get_settings()





def _run_async(coro):
    """Celery prefork 子进程内运行 async 协程；任务结束后释放 DB 连接池，避免 event loop 冲突。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            from app.database import engine

            loop.run_until_complete(engine.dispose())
        except Exception as exc:
            logger.warning("async engine dispose after celery task: %s", exc)
        asyncio.set_event_loop(None)
        loop.close()





async def _collect_group_creator_ids(group_id: int) -> list[int]:

    from sqlalchemy import select

    from app.models import MonitoredCreator



    async with async_session() as db:

        return list(

            (

                await db.execute(

                    select(MonitoredCreator.id).where(

                        MonitoredCreator.group_id == group_id,

                        MonitoredCreator.is_active == True,

                    )

                )

            ).scalars().all()

        )





async def _mark_hot_ingest_schedule(schedule_id: int) -> None:

    from datetime import datetime

    from sqlalchemy import select

    from app.models import CollectionSchedule



    async with async_session() as db:

        schedule = (

            await db.execute(select(CollectionSchedule).where(CollectionSchedule.id == schedule_id))

        ).scalar_one_or_none()

        if not schedule:

            return

        schedule.last_run_at = datetime.utcnow()

        if schedule.schedule_type == "once":

            schedule.executed = True

            schedule.enabled = False

        await db.commit()





@celery_app.task(

    name="app.tasks.jobs.scrape_creator_task",

    bind=True,

    max_retries=3,

    queue="scrape",

)

def scrape_creator_task(

    self,

    creator_id: int,

    mode: str = "daily",

    *,

    auto_historical: bool = False,

):

    async def _run():

        from sqlalchemy import select

        from sqlalchemy.orm import selectinload

        from app.models import MonitoredCreator

        from app.services.collection import _effective_scrape_mode



        async with async_session() as db:

            creator = (

                await db.execute(

                    select(MonitoredCreator)

                    .options(

                        selectinload(MonitoredCreator.group),

                        selectinload(MonitoredCreator.collection),

                    )

                    .where(MonitoredCreator.id == creator_id, MonitoredCreator.is_active == True)

                )

            ).scalar_one_or_none()

            if not creator:

                return {"creator_id": creator_id, "skipped": True, "reason": "not_found"}



            effective_mode = _effective_scrape_mode(creator, mode, auto_historical=auto_historical)

            stats = await collection_service.scrape_creator(db, creator, mode=effective_mode)

            await db.commit()

            return {

                "creator_id": creator_id,

                "mode": effective_mode,

                "new_videos": stats.new_videos,

                "updated_videos": stats.updated_videos,

                "skipped_videos": stats.skipped_videos,

            }



    try:

        return _run_async(_run())

    except Exception as exc:

        raise self.retry(exc=exc, countdown=300) from exc





@celery_app.task(name="app.tasks.jobs.scrape_group_task", queue="scrape")

def scrape_group_task(

    group_id: int,

    mode: str,

    *,

    auto_historical: bool = False,

    trigger: str = "task",

):

    """按博主拆分为独立 Celery 子任务（水平扩展）。"""

    creator_ids = _run_async(_collect_group_creator_ids(group_id))

    for creator_id in creator_ids:

        scrape_creator_task.delay(

            creator_id,

            mode,

            auto_historical=auto_historical,

        )

    return {

        "group_id": group_id,

        "mode": mode,

        "trigger": trigger,

        "dispatched": len(creator_ids),

    }





@celery_app.task(name="app.tasks.jobs.daily_schedule_task", queue="scrape")

def daily_schedule_task(schedule_id: int):

    async def _run():

        from datetime import datetime

        from sqlalchemy import select

        from app.models import MonitoredCreator, CollectionSchedule



        async with async_session() as db:

            schedule = (

                await db.execute(

                    select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)

                )

            ).scalar_one_or_none()

            if not schedule or not schedule.enabled or (schedule.task_type or "daily") != "daily":

                return {"schedule_id": schedule_id, "skipped": True}



            if schedule.group_id:

                creator_ids = (

                    await db.execute(

                        select(MonitoredCreator.id).where(

                            MonitoredCreator.group_id == schedule.group_id,

                            MonitoredCreator.is_active == True,

                        )

                    )

                ).scalars().all()

            else:

                creator_ids = (

                    await db.execute(

                        select(MonitoredCreator.id).where(MonitoredCreator.is_active == True)

                    )

                ).scalars().all()



            for creator_id in creator_ids:

                scrape_creator_task.delay(creator_id, "daily", auto_historical=True)



            schedule.last_run_at = datetime.utcnow()

            if schedule.schedule_type == "once":

                schedule.executed = True

                schedule.enabled = False

            await db.commit()

            return {"schedule_id": schedule_id, "dispatched": len(creator_ids)}



    return _run_async(_run())





@celery_app.task(name="app.tasks.jobs.hot_update_finalize_group_task", queue="scrape")

def hot_update_finalize_group_task(header_results, group_id: int, trigger: str):

    """B 线收尾：重判热门 + 清理不达标（chord 回调或空分组直接调用）。"""



    async def _run():

        from datetime import datetime

        from sqlalchemy import select

        from app.models import MonitorGroup

        from app.services.hot_refresh import reclassify_group_daily_hot, reconcile_daily_hot_records



        async with async_session() as db:

            reclassified = await reclassify_group_daily_hot(db, group_id)

            removed = await reconcile_daily_hot_records(db, group_id=group_id)

            group = (

                await db.execute(select(MonitorGroup).where(MonitorGroup.id == group_id))

            ).scalar_one_or_none()

            if group:

                group.last_hot_update_at = datetime.utcnow()

            await db.commit()

            return {

                "group_id": group_id,

                "reclassified": reclassified,

                "removed_hot": removed,

                "trigger": trigger,

                "skipped": False,

                "dispatched_workers": len(header_results or []),

            }



    return _run_async(_run())





@celery_app.task(name="app.tasks.jobs.hot_update_group_task", bind=True, max_retries=2, queue="scrape")

def hot_update_group_task(self, group_id: int, trigger: str = "scheduled"):

    if settings.local_mode:

        async def _run():

            from app.services.hot_refresh import run_hot_update_for_group



            async with async_session() as db:

                return await run_hot_update_for_group(db, group_id, trigger=trigger)



        try:

            return _run_async(_run())

        except Exception as exc:

            raise self.retry(exc=exc, countdown=120) from exc



    creator_ids = _run_async(_collect_group_creator_ids(group_id))

    if not creator_ids:

        return hot_update_finalize_group_task([], group_id, trigger)



    header = [scrape_creator_task.s(cid, "hot_update") for cid in creator_ids]

    chord(header)(hot_update_finalize_group_task.s(group_id, trigger))

    return {"group_id": group_id, "dispatched": len(creator_ids), "trigger": trigger}





@celery_app.task(name="app.tasks.jobs.hot_ingest_group_task", bind=True, max_retries=2, queue="scrape")

def hot_ingest_group_task(self, group_id: int, trigger: str = "schedule", schedule_id: Optional[int] = None):

    if settings.local_mode:

        async def _run():

            from datetime import datetime

            from sqlalchemy import select

            from app.models import CollectionSchedule

            from app.services.hot_refresh import run_hot_ingest_for_group



            async with async_session() as db:

                schedule = None

                if schedule_id:

                    schedule = (

                        await db.execute(

                            select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)

                        )

                    ).scalar_one_or_none()

                    if not schedule or not schedule.enabled:

                        return {"group_id": group_id, "skipped": True, "reason": "schedule_disabled"}

                result = await run_hot_ingest_for_group(db, group_id, trigger=trigger)

                if schedule is not None:

                    schedule.last_run_at = datetime.utcnow()

                    if schedule.schedule_type == "once":

                        schedule.executed = True

                        schedule.enabled = False

                    await db.commit()

                return result



        try:

            return _run_async(_run())

        except Exception as exc:

            raise self.retry(exc=exc, countdown=120) from exc



    if schedule_id:

        async def _validate_schedule():

            from sqlalchemy import select

            from app.models import CollectionSchedule



            async with async_session() as db:

                schedule = (

                    await db.execute(

                        select(CollectionSchedule).where(CollectionSchedule.id == schedule_id)

                    )

                ).scalar_one_or_none()

                return schedule is not None and schedule.enabled



        if not _run_async(_validate_schedule()):

            return {"group_id": group_id, "skipped": True, "reason": "schedule_disabled"}



    creator_ids = _run_async(_collect_group_creator_ids(group_id))

    chain_trigger = f"ingest_chain:{trigger}"

    if creator_ids:

        header = [scrape_creator_task.s(cid, "hot_ingest") for cid in creator_ids]

        chord(header)(hot_update_group_task.si(group_id, chain_trigger))

    else:

        hot_update_group_task.delay(group_id, chain_trigger)



    if schedule_id:

        _run_async(_mark_hot_ingest_schedule(schedule_id))



    return {"group_id": group_id, "dispatched": len(creator_ids), "trigger": trigger}





@celery_app.task(name="app.tasks.jobs.hot_update_coordinator_task", queue="scrape")

def hot_update_coordinator_task():

    async def _run():

        from app.services.hot_refresh import run_hot_update_all_due_groups



        async with async_session() as db:

            return await run_hot_update_all_due_groups(db, dispatch_only=True)



    return _run_async(_run())





@celery_app.task(name="app.tasks.jobs.purge_video_snapshots_task", queue="scrape")

def purge_video_snapshots_task():

    async def _run():

        from app.services.snapshot_archive import purge_old_video_snapshots



        async with async_session() as db:

            result = await purge_old_video_snapshots(db)

            return result



    return _run_async(_run())





@celery_app.task(name="app.tasks.jobs.postgres_backup_task", queue="scrape")

def postgres_backup_task():

    from app.services.postgres_backup import run_postgres_backup



    return run_postgres_backup()





@celery_app.task(name="app.tasks.jobs.scrape_all_creators_task", bind=True, max_retries=3, queue="scrape")

def scrape_all_creators_task(self):

    """全库采集：按博主拆分为独立 Worker 任务。"""



    async def _collect():

        from sqlalchemy import select

        from app.models import MonitoredCreator



        async with async_session() as db:

            return list(

                (

                    await db.execute(

                        select(MonitoredCreator.id).where(MonitoredCreator.is_active == True)

                    )

                ).scalars().all()

            )



    creator_ids = _run_async(_collect())

    for creator_id in creator_ids:

        scrape_creator_task.delay(creator_id, "daily", auto_historical=True)

    return {"dispatched": len(creator_ids)}


