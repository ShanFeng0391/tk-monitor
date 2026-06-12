from datetime import datetime
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    create_access_token, get_current_super_admin, get_current_user_manager, get_current_user,
    get_current_admin, hash_password, verify_password,
)
from app.core.roles import ROLE_SUPER_ADMIN, is_super_admin, is_tier_admin
from app.database import get_db
from app.models import User, MonitoredCreator, Video, Favorite, DataShare, VideoDramaRecognition, DramaStats, VideoSnapshot
from app.schemas import (
    Token, UserRegister, UserLogin, UserOut, UserStatusUpdate, AccessGatePublic,
    CreatorCreate, CreatorOut, CreatorUpdate, CreatorPasteRequest, CreatorPasteOut,
    CreatorBatchCreate, CreatorBatchCreateOut, CreatorBatchResultItem, VideoOut, VideoDetailOut, SnapshotOut,
    DramaScatterOut, DramaScatterPoint,
    FavoriteCreate, FavoriteUpdate, FavoriteBatchDelete, FavoriteOut, ShareCreate, ShareOut,
    DashboardStats, GrowthPoint, RecognitionOut, BatchRecognitionRequest,
    ViralPredictionOut, DashboardCollectionStatusOut,
    DramaOut, DramaDetailOut, RecognitionStats, PaginatedResponse, RecognitionManualUpdate, ScrapeResultOut,
    DramaMetadataLookupRequest, DramaMetadataLookupOut, DramaDoubaoPasteRequest,
)
from app.api.helpers import video_to_out, creator_to_out
from app.services.video_classifier import get_trend_data, get_view_velocities
from app.services.runtime_settings import runtime
from app.services import access_gate
from app.services.collection import collection_service
from app.services.doubao import recognition_service
from app.services.drama_stats import rebuild_all_drama_stats
from app.services.drama_metadata_providers import resolve_drama_assets
from app.services.scraper import scraper
from app.services.storage import load_cover_bytes
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1")


# ===== Auth =====
@router.get("/auth/access-gate", response_model=AccessGatePublic)
async def get_access_gate_public(db: AsyncSession = Depends(get_db)):
    return AccessGatePublic(**await access_gate.get_public(db))


@router.post("/auth/register", response_model=UserOut)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    if not await access_gate.verify(db, data.gate_answer):
        raise HTTPException(status_code=403, detail="访问密钥回答错误")
    clauses = [User.username == data.username]
    if data.email:
        clauses.append(User.email == data.email)
    existing = await db.execute(select(User).where(or_(*clauses)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在或邮箱已被使用")
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/auth/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    skip_gate = data.username == settings.admin_username
    if not skip_gate and not await access_gate.verify(db, data.gate_answer):
        raise HTTPException(status_code=403, detail="访问密钥回答错误")
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return Token(access_token=token)


@router.post("/auth/refresh", response_model=Token)
async def refresh_token(user: User = Depends(get_current_user)):
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return Token(access_token=token)


# ===== Users =====
@router.get("/users/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(admin: User = Depends(get_current_user_manager), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    if is_tier_admin(admin):
        users = [u for u in users if u.created_by_id == admin.id]
    return [UserOut.model_validate(u) for u in users]


@router.put("/users/{user_id}/status", response_model=UserOut)
async def update_user_status(
    user_id: int, data: UserStatusUpdate,
    admin: User = Depends(get_current_super_admin), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if is_super_admin(user):
        raise HTTPException(status_code=400, detail="Cannot disable super admin")
    user.is_active = data.is_active
    await db.flush()
    return user


# ===== Creators =====
async def _creator_to_out(db: AsyncSession, creator: MonitoredCreator, viewer: User) -> CreatorOut:
    return await creator_to_out(db, creator, viewer)


async def _video_to_out(db: AsyncSession, video: Video, user_id: Optional[int] = None) -> VideoOut:
    return await video_to_out(db, video, user_id)


async def _favorite_to_out(db: AsyncSession, fav: Favorite, user: User) -> FavoriteOut:
    video_out = await _video_to_out(db, fav.video, user.id)
    return FavoriteOut(
        id=fav.id,
        folder_name=fav.folder_name,
        note=fav.note,
        created_at=fav.created_at,
        video=video_out,
    )


@router.get("/creators", response_model=PaginatedResponse)
async def list_creators(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(MonitoredCreator)
    if group_id is not None:
        base = base.where(MonitoredCreator.group_id == group_id)
    count_q = select(func.count(MonitoredCreator.id))
    if group_id is not None:
        count_q = count_q.where(MonitoredCreator.group_id == group_id)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        base.order_by(MonitoredCreator.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    creators = result.scalars().all()
    items = [await _creator_to_out(db, c, user) for c in creators]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


async def _insert_monitored_creator(
    db: AsyncSession,
    user: User,
    raw_username: str,
    creator_info,
    group_id: int,
) -> MonitoredCreator:
    from app.services.creator_input import normalize_creator_username, ensure_creator_not_duplicate
    from app.services.group_helpers import get_active_group, ensure_group_has_capacity

    group = await get_active_group(db, group_id)
    await ensure_group_has_capacity(db, group)

    username = normalize_creator_username(raw_username)
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
    return creator


async def _add_monitored_creator(
    db: AsyncSession,
    user: User,
    raw_username: str,
    group_id: int,
) -> MonitoredCreator:
    if not group_id:
        raise HTTPException(status_code=400, detail="请选择博主类别")

    from app.services.creator_input import normalize_creator_username

    username = normalize_creator_username(raw_username)
    creator_info = await scraper.verify_creator(username)
    return await _insert_monitored_creator(db, user, raw_username, creator_info, group_id)


@router.post("/creators", response_model=CreatorOut, status_code=201)
async def add_creator(
    data: CreatorCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    creator = await _add_monitored_creator(db, user, data.tiktok_username, data.group_id)
    return await _creator_to_out(db, creator, user)


@router.post("/creators/parse-paste", response_model=CreatorPasteOut)
async def parse_creator_paste(
    data: CreatorPasteRequest,
    user: User = Depends(get_current_user),
):
    from app.services.creator_parse import parse_creator_paste as parse_paste

    try:
        usernames, source, tokens = await parse_paste(data.pasted_text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not usernames:
        raise HTTPException(status_code=404, detail="未能从文本中识别出博主账号，请检查内容或手动输入 @username")

    return CreatorPasteOut(usernames=usernames, source=source, tokens_used=tokens)


@router.post("/creators/batch", response_model=CreatorBatchCreateOut)
async def batch_add_creators(
    data: CreatorBatchCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.creator_input import normalize_username_list, normalize_creator_username

    usernames = normalize_username_list(data.tiktok_usernames)
    if not usernames:
        raise HTTPException(status_code=400, detail="没有有效的 @username")
    if not data.group_id:
        raise HTTPException(status_code=400, detail="请选择博主类别")

    results: list[CreatorBatchResultItem] = []
    succeeded = 0
    failed = 0
    sem = asyncio.Semaphore(4)

    async def verify_one(raw: str):
        async with sem:
            try:
                username = normalize_creator_username(raw)
                info = await scraper.verify_creator(username, fast=True)
                return raw, info, None
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                return raw, None, detail
            except Exception as exc:
                return raw, None, str(exc)

    verified = await asyncio.gather(*[verify_one(u) for u in usernames])

    for raw, creator_info, verify_error in verified:
        if verify_error:
            results.append(CreatorBatchResultItem(
                tiktok_username=raw,
                ok=False,
                message=verify_error,
            ))
            failed += 1
            continue
        try:
            creator = await _insert_monitored_creator(db, user, raw, creator_info, data.group_id)
            out = await _creator_to_out(db, creator, user)
            results.append(CreatorBatchResultItem(
                tiktok_username=raw,
                ok=True,
                message="添加成功",
                creator=out,
            ))
            succeeded += 1
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            results.append(CreatorBatchResultItem(
                tiktok_username=raw,
                ok=False,
                message=detail,
            ))
            failed += 1

    return CreatorBatchCreateOut(succeeded=succeeded, failed=failed, results=results)


@router.patch("/creators/{creator_id}", response_model=CreatorOut)
async def update_creator_category(
    creator_id: int,
    data: CreatorUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.creator_permissions import get_manageable_creator
    from app.services.group_helpers import get_active_group
    from app.services.collection import _resolve_thresholds
    from app.services.video_classifier import apply_video_classification
    from app.services.runtime_settings import runtime

    creator = await get_manageable_creator(db, creator_id, user)
    if creator.group_id == data.group_id:
        return await _creator_to_out(db, creator, user)

    group = await get_active_group(db, data.group_id)
    cnt = (await db.execute(
        select(func.count(MonitoredCreator.id)).where(MonitoredCreator.group_id == data.group_id)
    )).scalar() or 0
    if creator.group_id != data.group_id and cnt >= group.max_creators:
        raise HTTPException(status_code=400, detail=f"目标类别已达上限 ({group.max_creators})")

    creator.group_id = data.group_id
    await db.flush()

    refreshed = (await db.execute(
        select(MonitoredCreator)
        .options(selectinload(MonitoredCreator.group))
        .where(MonitoredCreator.id == creator.id)
    )).scalar_one()
    threshold = _resolve_thresholds(refreshed)
    videos = (await db.execute(select(Video).where(Video.creator_id == creator.id))).scalars().all()
    interval = threshold.growth_window_minutes
    for video in videos:
        await apply_video_classification(db, video, threshold, refreshed.tiktok_username, interval)

    return await _creator_to_out(db, refreshed, user)


@router.delete("/creators/{creator_id}", status_code=204)
async def delete_creator(
    creator_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from app.services.creator_permissions import get_manageable_creator

    creator = await get_manageable_creator(db, creator_id, user)
    await db.delete(creator)


@router.get("/creators/{creator_id}/stats")
async def creator_stats(
    creator_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MonitoredCreator).where(MonitoredCreator.id == creator_id))
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    stats = await db.execute(
        select(
            func.count(Video.id),
            func.coalesce(func.sum(Video.view_count), 0),
            func.coalesce(func.sum(Video.like_count), 0),
        ).where(Video.creator_id == creator.id)
    )
    row = stats.one()
    return {
        "creator_id": creator.id,
        "username": creator.tiktok_username,
        "video_count": row[0],
        "total_views": row[1],
        "total_likes": row[2],
    }


def _scrape_result_out(stats, mode: str) -> ScrapeResultOut:
    data = stats.to_dict()
    if mode == "historical":
        if data["fetched_videos"] == 0:
            msg = "未能从 TikTok 拉取视频列表，请检查代理池或稍后重试"
        else:
            msg = (
                f"数据采集完成：拉取 {data['fetched_videos']} 条，"
                f"新增 {data['new_videos']} 条，跳过 {data['skipped_videos']} 条"
            )
    else:
        msg = f"日常采集完成：新增 {data['new_videos']}，更新 {data['updated_videos']}，跳过 {data['skipped_videos']}"
    return ScrapeResultOut(message=msg, **data)


@router.post("/creators/{creator_id}/scrape/historical", response_model=ScrapeResultOut)
async def scrape_creator_historical(
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动触发：采集博主历史视频（已采集过的跳过，不重复更新）"""
    from app.services.creator_permissions import can_manage_creator

    result = await db.execute(
        select(MonitoredCreator)
        .options(selectinload(MonitoredCreator.group), selectinload(MonitoredCreator.collection))
        .where(MonitoredCreator.id == creator_id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    if not await can_manage_creator(db, user, creator):
        raise HTTPException(status_code=403, detail="无权操作其他账号添加的博主")

    from app.services.task_dispatch import dispatch_scrape_creator, use_worker_pool

    if use_worker_pool():
        queued = dispatch_scrape_creator(creator_id, "historical")
        return ScrapeResultOut(
            message=f"历史采集已加入 Worker 队列（task={queued['task_id']}）",
        )

    stats = await collection_service.scrape_creator(db, creator, mode="historical")
    return _scrape_result_out(stats, "historical")


@router.post("/creators/{creator_id}/scrape", response_model=ScrapeResultOut)
async def scrape_creator_daily(
    creator_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动触发：按日常策略增量更新（10 天内每 3 天更新，超过 10 天不更新）"""
    from app.services.creator_permissions import can_manage_creator

    result = await db.execute(
        select(MonitoredCreator)
        .options(selectinload(MonitoredCreator.group), selectinload(MonitoredCreator.collection))
        .where(MonitoredCreator.id == creator_id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    if not await can_manage_creator(db, user, creator):
        raise HTTPException(status_code=403, detail="无权操作其他账号添加的博主")

    from app.services.task_dispatch import dispatch_scrape_creator, use_worker_pool

    if use_worker_pool():
        queued = dispatch_scrape_creator(creator_id, "daily")
        return ScrapeResultOut(
            message=f"日常采集已加入 Worker 队列（task={queued['task_id']}）",
        )

    stats = await collection_service.scrape_creator(db, creator, mode="daily")
    return _scrape_result_out(stats, "daily")


# ===== Videos helpers =====
@router.get("/videos", response_model=PaginatedResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    creator_id: Optional[int] = None,
    drama_name: Optional[str] = None,
    sort_by: str = "published_at",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Video).options(selectinload(Video.creator), selectinload(Video.recognition))
    if category:
        cat_map = {"viral": "historical_viral", "hot": "daily_hot", "historical_viral": "historical_viral", "daily_hot": "daily_hot"}
        mapped = cat_map.get(category, category)
        if mapped == "historical_viral":
            query = query.where(Video.is_historical_viral == True)
        elif mapped == "daily_hot":
            query = query.where(Video.is_daily_hot == True)
        else:
            query = query.where(Video.category == category)
    if creator_id:
        query = query.where(Video.creator_id == creator_id)
    if drama_name:
        name = drama_name.strip().lstrip("《").rstrip("》")
        rec_ids = await db.execute(
            select(VideoDramaRecognition.video_id).where(
                VideoDramaRecognition.drama_name.ilike(f"%{name}%")
            )
        )
        ids = [r[0] for r in rec_ids.all()]
        if not ids:
            return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)
        query = query.where(Video.id.in_(ids))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    order_col = getattr(Video, sort_by, Video.published_at)
    query = query.order_by(order_col.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    videos = result.scalars().all()
    items = [await _video_to_out(db, v, user.id) for v in videos]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/videos/viral", response_model=PaginatedResponse)
async def viral_videos(
    page: int = 1, page_size: int = 20,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await list_videos(page=page, page_size=page_size, category="historical_viral", user=user, db=db)


@router.get("/videos/hot", response_model=PaginatedResponse)
async def hot_videos(
    page: int = 1, page_size: int = 20,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await list_videos(
        page=page, page_size=page_size, category="daily_hot",
        sort_by="instant_view_velocity", user=user, db=db,
    )


@router.get("/videos/{video_id}", response_model=VideoDetailOut)
async def get_video(
    video_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Video).options(selectinload(Video.creator), selectinload(Video.recognition))
        .where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    base = await _video_to_out(db, video, user.id)
    snapshots = await get_trend_data(db, video.video_id)
    rec = None
    if video.recognition:
        rec = await _recognition_to_out(video.recognition)

    return VideoDetailOut(
        **base.model_dump(),
        snapshots=[SnapshotOut.model_validate(s) for s in snapshots],
        recognition=rec,
    )


_INVALID_DRAMA_NAMES = {"未知", "非影视内容", ""}


async def _recognition_to_out(rec: VideoDramaRecognition) -> RecognitionOut:
    base = RecognitionOut.model_validate(rec)
    poster, page_url, source = await resolve_drama_assets(
        rec.drama_name or "",
        rec.drama_type or "",
        rec.analysis_reason or "",
    )
    return base.model_copy(update={
        "tmdb_poster_url": poster,
        "tmdb_url": page_url or base.tmdb_url,
        "metadata_source": source,
    })


async def _query_drama_scatter_points(
    db: AsyncSession,
    drama_name: str,
    current_video_id: Optional[int] = None,
) -> list[DramaScatterPoint]:
    if not drama_name or drama_name in _INVALID_DRAMA_NAMES:
        return []

    rows = (await db.execute(
        select(Video)
        .join(VideoDramaRecognition, VideoDramaRecognition.video_id == Video.id)
        .options(selectinload(Video.creator))
        .where(
            VideoDramaRecognition.drama_name == drama_name,
            Video.published_at.isnot(None),
        )
        .order_by(Video.published_at.asc())
    )).scalars().all()

    return [
        DramaScatterPoint(
            video_id=v.id,
            title=v.title,
            published_at=v.published_at,
            view_count=v.view_count or 0,
            creator_username=v.creator.tiktok_username if v.creator else None,
            is_current=current_video_id is not None and v.id == current_video_id,
        )
        for v in rows
    ]


@router.get("/videos/{video_id}/drama-scatter", response_model=DramaScatterOut)
async def video_drama_scatter(
    video_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同一影视剧下各视频的发布时间 × 播放量散点数据"""
    result = await db.execute(
        select(Video)
        .options(selectinload(Video.creator), selectinload(Video.recognition))
        .where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    drama_name = video.recognition.drama_name if video.recognition else None
    points = await _query_drama_scatter_points(db, drama_name, current_video_id=video_id)
    return DramaScatterOut(drama_name=drama_name, points=points)


@router.get("/dramas/{name}/scatter", response_model=DramaScatterOut)
async def drama_scatter(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """影视剧专题页：同剧视频发布时间 × 播放量散点"""
    result = await db.execute(select(DramaStats).where(DramaStats.drama_name == name))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Drama not found")
    points = await _query_drama_scatter_points(db, name)
    return DramaScatterOut(drama_name=name, points=points)


@router.get("/videos/{video_id}/trend", response_model=list[GrowthPoint])
async def video_trend(
    video_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    snapshots = await get_trend_data(db, video.video_id)
    return [
        GrowthPoint(snapshot_at=s.snapshot_at, view_count=s.view_count or 0, like_count=s.like_count or 0)
        for s in snapshots
    ]


@router.post("/videos/{video_id}/favorite", response_model=FavoriteOut)
async def add_favorite(
    video_id: int, data: FavoriteCreate = FavoriteCreate(),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Video).options(selectinload(Video.creator)).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    existing = await db.execute(
        select(Favorite).where(and_(Favorite.user_id == user.id, Favorite.video_id == video_id))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already favorited")

    fav = Favorite(
        user_id=user.id,
        video_id=video_id,
        folder_name=data.folder_name,
        note=(data.note or "").strip() or None,
    )
    db.add(fav)
    await db.flush()
    return await _favorite_to_out(db, fav, user)


@router.delete("/videos/{video_id}/favorite", status_code=204)
async def remove_favorite(
    video_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite).where(and_(Favorite.user_id == user.id, Favorite.video_id == video_id))
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")
    await db.delete(fav)


# ===== Favorites =====
@router.get("/favorites", response_model=list[FavoriteOut])
async def list_favorites(
    folder: Optional[str] = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    query = select(Favorite).options(selectinload(Favorite.video).selectinload(Video.creator)).where(Favorite.user_id == user.id)
    if folder:
        query = query.where(Favorite.folder_name == folder)
    result = await db.execute(query.order_by(Favorite.created_at.desc()))
    favorites = result.scalars().all()
    return [await _favorite_to_out(db, fav, user) for fav in favorites]


@router.patch("/favorites/{favorite_id}", response_model=FavoriteOut)
async def update_favorite(
    favorite_id: int,
    data: FavoriteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite)
        .options(selectinload(Favorite.video).selectinload(Video.creator))
        .where(and_(Favorite.id == favorite_id, Favorite.user_id == user.id))
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")

    if data.folder_name is not None:
        fav.folder_name = data.folder_name.strip() or "默认收藏夹"
    if data.note is not None:
        fav.note = data.note.strip() or None

    await db.flush()
    return await _favorite_to_out(db, fav, user)


@router.delete("/favorites/batch", status_code=204)
async def batch_remove_favorites(
    data: FavoriteBatchDelete,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Favorite).where(and_(Favorite.user_id == user.id, Favorite.id.in_(data.ids)))
    )
    for fav in result.scalars().all():
        await db.delete(fav)


# ===== Shares =====
@router.post("/shares", response_model=ShareOut, status_code=201)
async def create_share(
    data: ShareCreate, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Video).options(selectinload(Video.creator)).where(Video.id == data.video_id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    share = DataShare(admin_id=admin.id, target_user_id=data.target_user_id, video_id=data.video_id)
    db.add(share)
    await db.flush()
    video_out = await _video_to_out(db, video)
    target = await db.execute(select(User).where(User.id == data.target_user_id))
    target_user = target.scalar_one_or_none()
    return ShareOut(id=share.id, video=video_out, shared_at=share.shared_at, target_username=target_user.username if target_user else None)


@router.get("/shares", response_model=list[ShareOut])
async def list_shares(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DataShare).where(DataShare.admin_id == admin.id).order_by(DataShare.shared_at.desc())
    )
    shares = result.scalars().all()
    out = []
    for s in shares:
        v = await db.execute(select(Video).options(selectinload(Video.creator)).where(Video.id == s.video_id))
        video = v.scalar_one()
        target = await db.execute(select(User).where(User.id == s.target_user_id))
        tu = target.scalar_one_or_none()
        out.append(ShareOut(id=s.id, video=await _video_to_out(db, video), shared_at=s.shared_at, target_username=tu.username if tu else None))
    return out


@router.get("/shares/received", response_model=list[ShareOut])
async def received_shares(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DataShare).where(DataShare.target_user_id == user.id).order_by(DataShare.shared_at.desc())
    )
    shares = result.scalars().all()
    out = []
    for s in shares:
        v = await db.execute(select(Video).options(selectinload(Video.creator)).where(Video.id == s.video_id))
        video = v.scalar_one()
        out.append(ShareOut(id=s.id, video=await _video_to_out(db, video), shared_at=s.shared_at))
    return out


@router.delete("/shares/{share_id}", status_code=204)
async def delete_share(share_id: int, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DataShare).where(DataShare.id == share_id))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    await db.delete(share)


# ===== Dashboard =====
@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if group_id is not None:
        total_creators = (await db.execute(
            select(func.count(MonitoredCreator.id)).where(MonitoredCreator.group_id == group_id)
        )).scalar() or 0
        stats = await db.execute(
            select(
                func.count(Video.id),
                func.sum(case((Video.is_historical_viral == True, 1), else_=0)),
                func.sum(case((Video.is_daily_hot == True, 1), else_=0)),
                func.coalesce(func.sum(Video.view_count), 0),
                func.coalesce(func.sum(Video.like_count), 0),
            )
            .select_from(Video)
            .join(MonitoredCreator, MonitoredCreator.id == Video.creator_id)
            .where(MonitoredCreator.group_id == group_id)
        )
    else:
        total_creators = (await db.execute(select(func.count(MonitoredCreator.id)))).scalar() or 0
        stats = await db.execute(
            select(
                func.count(Video.id),
                func.sum(case((Video.is_historical_viral == True, 1), else_=0)),
                func.sum(case((Video.is_daily_hot == True, 1), else_=0)),
                func.coalesce(func.sum(Video.view_count), 0),
                func.coalesce(func.sum(Video.like_count), 0),
            )
        )
    row = stats.one()
    return DashboardStats(
        total_creators=total_creators,
        total_videos=row[0] or 0,
        viral_count=row[1] or 0,
        hot_count=row[2] or 0,
        total_views=row[3] or 0,
        total_likes=row[4] or 0,
    )


@router.get("/dashboard/collection-status", response_model=DashboardCollectionStatusOut)
async def dashboard_collection_status(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.collection_status import build_collection_status

    data = await build_collection_status(db, group_id=group_id)
    return DashboardCollectionStatusOut(**data)


@router.get("/dashboard/growth")
async def dashboard_growth(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.group_helpers import video_in_group

    query = (
        select(Video)
        .options(selectinload(Video.recognition))
        .where(Video.is_daily_hot == True)
    )
    if group_id is not None:
        query = query.where(video_in_group(group_id))
    hot_vids = await db.execute(
        query.order_by(Video.avg_view_velocity.desc(), Video.instant_view_velocity.desc()).limit(10)
    )
    videos = hot_vids.scalars().all()
    items = []
    for v in videos:
        avg, instant = await get_view_velocities(db, v, runtime.int("growth_window_minutes"))
        snap_count = (
            await db.execute(
                select(func.count(VideoSnapshot.id)).where(VideoSnapshot.video_id == v.video_id)
            )
        ).scalar() or 0
        rec = v.recognition
        drama_name = rec.drama_name if rec and rec.drama_name else None
        content_type = v.content_type or (rec.drama_type if rec else None)
        items.append(
            {
                "id": v.id,
                "drama_name": drama_name,
                "content_type": content_type,
                "published_at": v.published_at,
                "view_count": v.view_count,
                "avg_view_velocity": avg,
                "instant_view_velocity": instant,
                "velocity_ready": snap_count >= 2,
                "view_growth": instant,
                "like_growth": avg,
            }
        )
    return {"items": items}


@router.get("/dashboard/viral-predictions", response_model=ViralPredictionOut)
async def dashboard_viral_predictions(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.viral_prediction import build_viral_predictions

    data = await build_viral_predictions(db, group_id=group_id)
    return ViralPredictionOut(**data)


@router.get("/dashboard/creators")
async def dashboard_creators(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MonitoredCreator).order_by(MonitoredCreator.created_at.desc()))
    creators = result.scalars().all()
    out = []
    for c in creators:
        stats = await db.execute(
            select(func.count(Video.id), func.coalesce(func.sum(Video.view_count), 0))
            .where(Video.creator_id == c.id)
        )
        row = stats.one()
        out.append({
            "id": c.id,
            "username": c.tiktok_username,
            "display_name": c.display_name,
            "video_count": row[0],
            "total_views": row[1],
            "is_active": c.is_active,
        })
    return out


# ===== Recognition =====
async def _resolve_cover_bytes(video: Video) -> bytes | None:
    data = load_cover_bytes(video.video_id, video.cover_url, video.cover_local_path)
    if data:
        return data
    if video.cover_url and video.cover_url.startswith(("http://", "https://")):
        return await scraper.download_cover(video.cover_url)
    return None


@router.post("/recognition/parse-doubao-paste", response_model=DramaMetadataLookupOut)
async def parse_doubao_paste(
    data: DramaDoubaoPasteRequest,
    user: User = Depends(get_current_user),
):
    """粘贴豆包识别长文 → AI 提取字段；TMDB 仅作参考链接补充。"""
    try:
        parsed, _log, tokens = await recognition_service.parse_doubao_paste(data.pasted_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if parsed.get("drama_name") in ("未知", "《信息不足》"):
        raise HTTPException(status_code=404, detail="未能从粘贴内容中识别出影视作品，请检查内容或手动填写")

    return DramaMetadataLookupOut(
        drama_name=parsed["drama_name"],
        drama_type=parsed.get("drama_type") or "未知",
        english_name=parsed.get("english_name") or "",
        release_year=parsed.get("release_year") or "",
        actors=parsed.get("actors") or "",
        director=parsed.get("director") or "",
        summary=parsed.get("summary") or "",
        source=parsed.get("source") or "doubao_paste",
        verified=bool(parsed.get("verified")),
        tmdb_id=parsed.get("tmdb_id"),
        tmdb_url=parsed.get("tmdb_url") or "",
        tmdb_ref_note=parsed.get("tmdb_ref_note") or "",
        bangumi_id=parsed.get("bangumi_id"),
        metadata_source=parsed.get("metadata_source"),
        tokens_used=tokens,
    )


@router.post("/recognition/lookup-metadata", response_model=DramaMetadataLookupOut)
async def lookup_drama_metadata(
    data: DramaMetadataLookupRequest,
    user: User = Depends(get_current_user),
):
    """按片名补全（动漫 Bangumi / 其它 TMDB）；标注主流程请用 parse-doubao-paste。"""
    try:
        parsed, _log, tokens = await recognition_service.lookup_drama_metadata(data.drama_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if parsed.get("drama_name") in ("未知", "《信息不足》"):
        raise HTTPException(status_code=404, detail="未找到该作品，请检查片名或手动填写")

    return DramaMetadataLookupOut(
        drama_name=parsed["drama_name"],
        drama_type=parsed.get("drama_type") or "未知",
        english_name=parsed.get("english_name") or "",
        release_year=parsed.get("release_year") or "",
        actors=parsed.get("actors") or "",
        director="",
        summary="",
        source=parsed.get("source") or "unknown",
        verified=bool(parsed.get("verified")),
        tmdb_id=parsed.get("tmdb_id"),
        tmdb_url=parsed.get("tmdb_url") or "",
        tmdb_ref_note="",
        bangumi_id=parsed.get("bangumi_id"),
        metadata_source=parsed.get("metadata_source"),
        tokens_used=tokens,
    )


@router.put("/videos/{video_id}/recognition", response_model=RecognitionOut)
async def update_recognition_manual(
    video_id: int,
    data: RecognitionManualUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """人工标注影视剧（准确数据来源）。"""
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rec = (await db.execute(
        select(VideoDramaRecognition).where(VideoDramaRecognition.video_id == video_id)
    )).scalar_one_or_none()
    if not rec:
        rec = VideoDramaRecognition(video_id=video_id, status="pending")
        db.add(rec)
        await db.flush()

    if not data.drama_name or not data.drama_name.strip():
        raise HTTPException(status_code=400, detail="请填写影视剧名称")

    prior_name = rec.drama_name
    rec = await recognition_service.save_manual_recognition(
        db,
        video,
        rec,
        drama_name=data.drama_name,
        drama_type=data.drama_type,
        actors=data.actors,
        analysis_reason=data.analysis_reason or "人工标注",
        user_id=user.id,
        prior_drama_name=prior_name,
    )

    return await _recognition_to_out(rec)


@router.get("/videos/{video_id}/recognition", response_model=RecognitionOut)
async def get_recognition(
    video_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VideoDramaRecognition).where(VideoDramaRecognition.video_id == video_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recognition not found")
    return await _recognition_to_out(rec)


@router.post("/recognition/batch")
async def batch_recognition(
    data: BatchRecognitionRequest, admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    raise HTTPException(
        status_code=410,
        detail="已关闭 AI 封面识别，请逐条人工标注；推荐 POST /recognition/parse-doubao-paste 粘贴豆包识别结果",
    )


@router.get("/dramas", response_model=list[DramaOut])
async def list_dramas(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.group_helpers import list_dramas_for_group

    rows = await list_dramas_for_group(db, group_id)
    return [DramaOut(**row) for row in rows]


@router.get("/dramas/trending", response_model=list[DramaOut])
async def trending_dramas(
    group_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.group_helpers import list_dramas_for_group

    rows = await list_dramas_for_group(db, group_id, trending=True, limit=20)
    return [DramaOut(**row) for row in rows]


@router.get("/dramas/{name}", response_model=DramaDetailOut)
async def get_drama(name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DramaStats).where(DramaStats.drama_name == name))
    drama = result.scalar_one_or_none()
    if not drama:
        raise HTTPException(status_code=404, detail="Drama not found")

    rec = (await db.execute(
        select(VideoDramaRecognition)
        .where(
            VideoDramaRecognition.drama_name == name,
            VideoDramaRecognition.status == "success",
        )
        .order_by(
            VideoDramaRecognition.is_manual_override.desc(),
            VideoDramaRecognition.completed_at.desc(),
        )
        .limit(1)
    )).scalar_one_or_none()
    recognition = await _recognition_to_out(rec) if rec else None
    base = DramaOut.model_validate(drama)
    return DramaDetailOut(**base.model_dump(), recognition=recognition)


@router.post("/dramas/rebuild-stats")
async def rebuild_drama_stats(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """全量重算影视剧聚合统计（修复测试期间累加失真）。"""
    count = await rebuild_all_drama_stats(db)
    return {"ok": True, "drama_count": count}


@router.get("/recognition/stats", response_model=RecognitionStats)
async def recognition_stats(admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(VideoDramaRecognition.id)))).scalar() or 0
    pending = (await db.execute(select(func.count(VideoDramaRecognition.id)).where(VideoDramaRecognition.status == "pending"))).scalar() or 0
    success = (await db.execute(select(func.count(VideoDramaRecognition.id)).where(VideoDramaRecognition.status == "success"))).scalar() or 0
    failed = (await db.execute(select(func.count(VideoDramaRecognition.id)).where(VideoDramaRecognition.status == "failed"))).scalar() or 0
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    cost = (await db.execute(
        select(func.coalesce(func.sum(VideoDramaRecognition.api_cost), 0))
        .where(VideoDramaRecognition.created_at >= today)
    )).scalar() or 0
    return RecognitionStats(total=total, pending=pending, success=success, failed=failed, daily_cost=float(cost), daily_budget=runtime.float("recognition_daily_budget"))


# ===== Export =====
@router.get("/export/videos")
async def export_videos(
    format: str = "csv",
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    import csv
    import io

    result = await db.execute(
        select(Video).options(selectinload(Video.creator)).order_by(Video.published_at.desc())
    )
    videos = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["video_id", "title", "creator", "views", "likes", "shares", "comments", "category", "published_at"])
    for v in videos:
        writer.writerow([
            v.video_id, v.title, v.creator.tiktok_username if v.creator else "",
            v.view_count, v.like_count, v.share_count, v.comment_count,
            v.category, v.published_at.isoformat() if v.published_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=videos.csv"},
    )
