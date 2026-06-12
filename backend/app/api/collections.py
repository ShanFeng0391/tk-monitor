from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models import UserCollection, MonitoredCreator, User
from app.schemas import (
    UserCollectionCreate, UserCollectionUpdate, UserCollectionOut,
    CreatorCreate, CreatorOut, ScrapeResultOut,
)
from app.services.scraper import scraper
from app.services.collection import collection_service
from app.services.creator_permissions import get_manageable_creator, get_owned_collection_or_403

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


def _collection_out(col: UserCollection, creator_count: int = 0) -> UserCollectionOut:
    return UserCollectionOut(
        id=col.id,
        name=col.name,
        description=col.description,
        historical_view_threshold=col.historical_view_threshold,
        daily_hot_avg_growth_threshold=float(col.daily_hot_avg_growth_threshold or 50.0),
        growth_window_minutes=col.growth_window_minutes,
        scrape_window_hours=col.scrape_window_hours,
        max_creators=col.max_creators,
        is_active=col.is_active,
        creator_count=creator_count,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.get("", response_model=list[UserCollectionOut])
async def list_collections(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    cols = (await db.execute(
        select(UserCollection).where(UserCollection.user_id == user.id).order_by(UserCollection.created_at.desc())
    )).scalars().all()
    out = []
    for col in cols:
        cnt = (await db.execute(
            select(func.count(MonitoredCreator.id)).where(MonitoredCreator.collection_id == col.id)
        )).scalar() or 0
        out.append(_collection_out(col, cnt))
    return out


@router.post("", response_model=UserCollectionOut, status_code=201)
async def create_collection(
    data: UserCollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = UserCollection(user_id=user.id, **data.model_dump())
    db.add(col)
    await db.flush()
    return _collection_out(col, 0)


@router.get("/{collection_id}", response_model=UserCollectionOut)
async def get_collection(
    collection_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(
            and_(UserCollection.id == collection_id, UserCollection.user_id == user.id)
        )
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    cnt = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.collection_id == col.id)
    )).scalar() or 0
    return _collection_out(col, cnt)


@router.put("/{collection_id}", response_model=UserCollectionOut)
async def update_collection(
    collection_id: int,
    data: UserCollectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(
            and_(UserCollection.id == collection_id, UserCollection.user_id == user.id)
        )
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(col, k, v)
    await db.flush()
    cnt = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.collection_id == col.id)
    )).scalar() or 0
    return _collection_out(col, cnt)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(
            and_(UserCollection.id == collection_id, UserCollection.user_id == user.id)
        )
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(col)


@router.get("/{collection_id}/creators", response_model=list[CreatorOut])
async def list_collection_creators(
    collection_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(
            and_(UserCollection.id == collection_id, UserCollection.user_id == user.id)
        )
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    creators = (await db.execute(
        select(MonitoredCreator).where(MonitoredCreator.collection_id == collection_id)
    )).scalars().all()
    from app.api.helpers import creator_to_out
    return [await creator_to_out(db, c, user) for c in creators]


@router.post("/{collection_id}/creators", response_model=CreatorOut, status_code=201)
async def add_collection_creator(
    collection_id: int,
    data: CreatorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    col = (await db.execute(
        select(UserCollection).where(
            and_(UserCollection.id == collection_id, UserCollection.user_id == user.id)
        )
    )).scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    cnt = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.collection_id == collection_id)
    )).scalar() or 0
    if cnt >= col.max_creators:
        raise HTTPException(status_code=400, detail=f"Collection creator limit reached ({col.max_creators})")

    from app.services.creator_input import normalize_creator_username, ensure_creator_not_duplicate

    username = normalize_creator_username(data.tiktok_username)
    creator_info = await scraper.verify_creator(username)
    if not creator_info.exists:
        raise HTTPException(status_code=404, detail="TikTok creator not found")

    canonical = (creator_info.username or username).lower()
    await ensure_creator_not_duplicate(db, canonical, tiktok_user_id=creator_info.user_id)

    creator = MonitoredCreator(
        user_id=user.id,
        collection_id=collection_id,
        tiktok_username=creator_info.username or username,
        tiktok_user_id=creator_info.user_id,
        display_name=creator_info.display_name,
        follower_count=creator_info.follower_count or 0,
    )
    db.add(creator)
    await db.flush()
    from app.api.helpers import creator_to_out
    return await creator_to_out(db, creator, user)


@router.delete("/{collection_id}/creators/{creator_id}", status_code=204)
async def remove_collection_creator(
    collection_id: int,
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_collection_or_403(db, collection_id, user)
    creator = await get_manageable_creator(db, creator_id, user)
    if creator.collection_id != collection_id:
        raise HTTPException(status_code=404, detail="Creator not found")
    await db.delete(creator)


@router.post("/{collection_id}/creators/{creator_id}/scrape/historical", response_model=ScrapeResultOut)
async def scrape_collection_creator_historical(
    collection_id: int,
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_collection_or_403(db, collection_id, user)
    creator = await get_manageable_creator(db, creator_id, user)
    if creator.collection_id != collection_id:
        raise HTTPException(status_code=404, detail="Creator not found")

    creator = (await db.execute(
        select(MonitoredCreator)
        .options(selectinload(MonitoredCreator.collection), selectinload(MonitoredCreator.group))
        .where(MonitoredCreator.id == creator_id)
    )).scalar_one()

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
