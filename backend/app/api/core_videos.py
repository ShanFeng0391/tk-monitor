from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models import (
    User, Video, MonitoredCreator, HistoricalViralArchive,
    DailyHotRecord, UserCollection, VideoDramaRecognition,
)
from app.schemas import PaginatedResponse, HistoricalViralOut, DailyHotOut
from app.api.helpers import video_to_out
from app.config import get_settings
from app.services.group_helpers import archive_in_group, daily_hot_in_group

settings = get_settings()
router = APIRouter(prefix="/api/v1/core", tags=["core"])


@router.get("/historical-viral", response_model=PaginatedResponse)
async def search_historical_viral(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    creator_username: Optional[str] = None,
    creator_id: Optional[int] = None,
    drama_name: Optional[str] = None,
    content_type: Optional[str] = None,
    min_views: Optional[int] = None,
    max_views: Optional[int] = None,
    min_followers: Optional[int] = None,
    max_followers: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "archived_at",
    group_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(HistoricalViralArchive).options(
        selectinload(HistoricalViralArchive.video).selectinload(Video.creator),
        selectinload(HistoricalViralArchive.video).selectinload(Video.recognition),
    )
    if group_id is not None:
        query = query.where(archive_in_group(group_id))
    if keyword:
        kw = keyword.strip().lstrip("《").rstrip("》")
        if kw:
            query = query.where(
                or_(
                    HistoricalViralArchive.content_type.ilike(f"%{kw}%"),
                    HistoricalViralArchive.video.has(Video.content_type.ilike(f"%{kw}%")),
                    HistoricalViralArchive.video.has(
                        Video.recognition.has(
                            or_(
                                VideoDramaRecognition.drama_name.ilike(f"%{kw}%"),
                                VideoDramaRecognition.drama_type.ilike(f"%{kw}%"),
                            )
                        )
                    ),
                )
            )
    if creator_username:
        query = query.where(HistoricalViralArchive.creator_username.ilike(f"%{creator_username.lstrip('@')}%"))
    if creator_id is not None:
        query = query.where(HistoricalViralArchive.video.has(Video.creator_id == creator_id))
    if drama_name:
        name = drama_name.strip().lstrip("《").rstrip("》")
        if name:
            query = (
                query.join(Video, HistoricalViralArchive.video_id == Video.id)
                .join(VideoDramaRecognition, VideoDramaRecognition.video_id == Video.id)
                .where(VideoDramaRecognition.drama_name.ilike(f"%{name}%"))
            )
    if content_type:
        ct = content_type.strip()
        if ct:
            query = query.where(
                or_(
                    HistoricalViralArchive.content_type.ilike(f"%{ct}%"),
                    HistoricalViralArchive.video.has(Video.content_type.ilike(f"%{ct}%")),
                    HistoricalViralArchive.video.has(
                        Video.recognition.has(VideoDramaRecognition.drama_type.ilike(f"%{ct}%"))
                    ),
                )
            )
    if min_views is not None:
        query = query.where(HistoricalViralArchive.view_count >= min_views)
    if max_views is not None:
        query = query.where(HistoricalViralArchive.view_count <= max_views)
    if min_followers is not None or max_followers is not None:
        follower_conditions = []
        follower_col = func.coalesce(MonitoredCreator.follower_count, 0)
        if min_followers is not None:
            follower_conditions.append(follower_col >= min_followers)
        if max_followers is not None:
            follower_conditions.append(follower_col <= max_followers)
        query = query.where(
            HistoricalViralArchive.video.has(
                Video.creator.has(and_(*follower_conditions))
            )
        )
    if date_from:
        query = query.where(HistoricalViralArchive.archived_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.where(HistoricalViralArchive.archived_at <= datetime.combine(date_to, datetime.max.time()))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    order_map = {
        "archived_at": HistoricalViralArchive.archived_at,
        "view_count": HistoricalViralArchive.view_count,
        "published_at": HistoricalViralArchive.published_at,
    }
    order_col = order_map.get(sort_by, HistoricalViralArchive.archived_at)
    rows = (await db.execute(
        query.order_by(order_col.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for arch in rows:
        if arch.video:
            base = await video_to_out(db, arch.video, user.id)
            items.append(HistoricalViralOut(
                **base.model_dump(),
                archive_id=arch.id,
                threshold_used=arch.threshold_used,
                archived_at=arch.archived_at,
            ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/historical-viral/stats")
async def historical_viral_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(HistoricalViralArchive.id)))).scalar() or 0
    by_type = await db.execute(
        select(HistoricalViralArchive.content_type, func.count(HistoricalViralArchive.id))
        .group_by(HistoricalViralArchive.content_type)
    )
    return {"total": total, "by_content_type": {row[0] or "未标注": row[1] for row in by_type.all()}}


@router.get("/daily-hot", response_model=PaginatedResponse)
async def list_daily_hot_market(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    hot_date: Optional[date] = None,
    content_type: Optional[str] = None,
    min_growth: Optional[float] = None,
    group_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_date = hot_date or date.today()
    query = (
        select(DailyHotRecord)
        .join(Video, DailyHotRecord.video_id == Video.id)
        .options(selectinload(DailyHotRecord.video).selectinload(Video.creator))
        .options(selectinload(DailyHotRecord.video).selectinload(Video.recognition))
        .where(DailyHotRecord.hot_date == target_date)
    )
    if group_id is not None:
        query = query.where(daily_hot_in_group(group_id))
    if content_type:
        query = query.where(Video.content_type == content_type)
    if min_growth is not None:
        query = query.where(DailyHotRecord.view_growth >= min_growth)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    records = (await db.execute(
        query.order_by(DailyHotRecord.view_growth.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for rec in records:
        base = await video_to_out(db, rec.video, user.id)
        items.append(DailyHotOut(
            **base.model_dump(),
            record_id=rec.id,
            hot_date=rec.hot_date,
            view_threshold_used=rec.view_threshold_used,
            growth_threshold_used=rec.growth_threshold_used,
            detected_at=rec.detected_at,
        ))
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/daily-hot/stats")
async def daily_hot_stats(
    hot_date: Optional[date] = None,
    group_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_date = hot_date or date.today()
    count_query = select(func.count(DailyHotRecord.id)).where(DailyHotRecord.hot_date == target_date)
    avg_growth_query = select(func.avg(DailyHotRecord.avg_view_velocity)).where(DailyHotRecord.hot_date == target_date)
    avg_instant_query = select(func.avg(DailyHotRecord.view_growth)).where(DailyHotRecord.hot_date == target_date)
    if group_id is not None:
        count_query = count_query.where(daily_hot_in_group(group_id))
        avg_growth_query = avg_growth_query.where(daily_hot_in_group(group_id))
        avg_instant_query = avg_instant_query.where(daily_hot_in_group(group_id))
    count = (await db.execute(count_query)).scalar() or 0
    avg_growth = (await db.execute(avg_growth_query)).scalar() or 0
    avg_instant = (await db.execute(avg_instant_query)).scalar() or 0
    return {
        "hot_date": str(target_date),
        "count": count,
        "avg_growth": round(float(avg_growth), 2),
        "avg_instant_velocity": round(float(avg_instant), 2),
    }


@router.get("/collections/{collection_id}/daily-hot", response_model=PaginatedResponse)
async def collection_daily_hot(
    collection_id: int,
    page: int = 1,
    page_size: int = 20,
    hot_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(and_(UserCollection.id == collection_id, UserCollection.user_id == user.id))
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    creator_ids = list((await db.execute(
        select(MonitoredCreator.id).where(MonitoredCreator.collection_id == collection_id)
    )).scalars().all())
    if not creator_ids:
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)

    target_date = hot_date or date.today()
    query = (
        select(DailyHotRecord)
        .join(Video, DailyHotRecord.video_id == Video.id)
        .options(selectinload(DailyHotRecord.video).selectinload(Video.creator))
        .options(selectinload(DailyHotRecord.video).selectinload(Video.recognition))
        .where(and_(DailyHotRecord.hot_date == target_date, Video.creator_id.in_(creator_ids)))
    )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    records = (await db.execute(
        query.order_by(DailyHotRecord.view_growth.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = []
    for rec in records:
        base = await video_to_out(db, rec.video, user.id)
        items.append(DailyHotOut(
            **base.model_dump(),
            record_id=rec.id,
            hot_date=rec.hot_date,
            view_threshold_used=rec.view_threshold_used,
            growth_threshold_used=rec.growth_threshold_used,
            detected_at=rec.detected_at,
        ))
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
