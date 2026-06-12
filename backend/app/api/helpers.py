from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import Video, Favorite, MonitoredCreator, User, VideoDramaRecognition, MonitorGroup
from app.schemas import VideoOut, CreatorOut
from app.services.video_classifier import get_view_velocities
from app.services.creator_permissions import can_manage_creator
from app.services.tiktok_url import resolve_video_url
from app.services.runtime_settings import runtime


async def creator_to_out(
    db: AsyncSession,
    creator: MonitoredCreator,
    viewer: Optional[User] = None,
) -> CreatorOut:
    count_result = await db.execute(
        select(func.count(Video.id)).where(Video.creator_id == creator.id)
    )
    owner_username = None
    if viewer:
        owner = (await db.execute(select(User).where(User.id == creator.user_id))).scalar_one_or_none()
        owner_username = owner.username if owner else None

    can_delete = True
    if viewer:
        can_delete = await can_manage_creator(db, viewer, creator)

    group_name = None
    if creator.group_id:
        group = (await db.execute(
            select(MonitorGroup).where(MonitorGroup.id == creator.group_id)
        )).scalar_one_or_none()
        group_name = group.name if group else None

    return CreatorOut(
        id=creator.id,
        tiktok_username=creator.tiktok_username,
        tiktok_user_id=creator.tiktok_user_id,
        display_name=creator.display_name,
        follower_count=creator.follower_count or 0,
        is_active=creator.is_active,
        created_at=creator.created_at,
        last_scraped_at=creator.last_scraped_at,
        last_hot_ingest_at=creator.last_hot_ingest_at,
        last_hot_update_at=creator.last_hot_update_at,
        historical_scraped_at=creator.historical_scraped_at,
        video_count=count_result.scalar() or 0,
        user_id=creator.user_id,
        owner_username=owner_username,
        group_id=creator.group_id,
        group_name=group_name,
        can_delete=can_delete,
    )


async def video_to_out(db: AsyncSession, video: Video, user_id: Optional[int] = None) -> VideoOut:
    avg_velocity, instant_velocity = await get_view_velocities(
        db, video, runtime.int("growth_window_minutes")
    )
    creator_username = video.creator.tiktok_username if video.creator else None
    creator_id = video.creator_id
    creator_follower_count = (video.creator.follower_count or 0) if video.creator else 0

    drama_name = (await db.execute(
        select(VideoDramaRecognition.drama_name, VideoDramaRecognition.drama_type)
        .where(VideoDramaRecognition.video_id == video.id)
    )).first()
    drama_name_val = drama_name.drama_name if drama_name else None
    drama_type_val = drama_name.drama_type if drama_name else None

    is_favorited = False
    if user_id:
        fav = await db.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.video_id == video.id)
        )
        is_favorited = fav.scalar_one_or_none() is not None

    return VideoOut(
        id=video.id,
        video_id=video.video_id,
        title=video.title,
        description=video.description,
        video_url=resolve_video_url(
            video_id=video.video_id,
            creator_username=creator_username,
            source_username=getattr(video, "source_username", None),
            stored_url=video.video_url,
        ),
        cover_url=video.cover_url,
        cover_local_path=video.cover_local_path,
        published_at=video.published_at,
        duration=video.duration,
        view_count=video.view_count or 0,
        like_count=video.like_count or 0,
        share_count=video.share_count or 0,
        comment_count=video.comment_count or 0,
        category=video.category or "normal",
        content_type=video.content_type,
        traffic_grade=video.traffic_grade,
        is_featured=video.is_featured or False,
        is_historical_viral=video.is_historical_viral or False,
        is_daily_hot=video.is_daily_hot or False,
        daily_hot_growth=video.daily_hot_growth if video.daily_hot_growth is not None else instant_velocity,
        avg_view_velocity=avg_velocity,
        instant_view_velocity=instant_velocity,
        creator_username=creator_username,
        creator_id=creator_id,
        creator_follower_count=creator_follower_count,
        drama_name=drama_name_val,
        drama_type=drama_type_val,
        view_growth=instant_velocity,
        like_growth=None,
        is_favorited=is_favorited,
    )
