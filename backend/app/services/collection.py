import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.services.runtime_settings import runtime
from app.models import MonitoredCreator, Video, VideoSnapshot
from app.services.thresholds import (
    thresholds_from_group, thresholds_from_collection, get_default_thresholds,
)
from app.services.video_classifier import apply_video_classification
from app.services.collection_policy import (
    should_update_existing_video,
    should_update_for_hot_refresh,
    scrape_window_hours,
    hot_fetch_window_hours,
    should_ingest_new_for_hot,
    should_update_for_hot_update,
)
from app.services.video_classifier import check_historical_viral
from app.services.scraper import scraper
from app.services.proxy_pool import proxy_pool
from app.services.storage import load_cover_bytes
from app.services.storage import store_cover

settings = get_settings()
ScrapeMode = Literal["historical", "daily", "hot_refresh", "hot_ingest", "hot_update"]


@dataclass
class ScrapeStats:
    new_videos: int = 0
    updated_videos: int = 0
    skipped_videos: int = 0
    fetched_videos: int = 0

    def to_dict(self):
        return {
            "new_videos": self.new_videos,
            "updated_videos": self.updated_videos,
            "skipped_videos": self.skipped_videos,
            "fetched_videos": self.fetched_videos,
            "total_processed": self.new_videos + self.updated_videos + self.skipped_videos,
        }


async def _flush_with_retry(db: AsyncSession, retries: int = 6) -> None:
    for attempt in range(retries):
        try:
            await db.flush()
            return
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt >= retries - 1:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))


def _resolve_thresholds(creator: MonitoredCreator):
    if creator.group:
        return thresholds_from_group(creator.group)
    if creator.collection:
        return thresholds_from_collection(creator.collection)
    return get_default_thresholds()


def _effective_scrape_mode(
    creator: MonitoredCreator,
    mode: ScrapeMode,
    *,
    auto_historical: bool,
) -> ScrapeMode:
    """定时闹钟：未做过历史采集的博主先走 historical，再进入 daily。"""
    if auto_historical and mode == "daily" and not creator.historical_scraped_at:
        return "historical"
    return mode


def _snapshot_source(mode: ScrapeMode) -> str:
    if mode == "hot_ingest":
        return "hot_ingest"
    if mode in ("hot_update", "hot_refresh"):
        return "hot_update"
    return "daily"


class CollectionService:
    async def scrape_creator(
        self,
        db: AsyncSession,
        creator: MonitoredCreator,
        mode: ScrapeMode = "daily",
    ) -> ScrapeStats:
        if not creator.is_active:
            return ScrapeStats()

        threshold = _resolve_thresholds(creator)
        if mode in ("hot_ingest", "hot_update"):
            window_hours = hot_fetch_window_hours(threshold.scrape_window_hours)
        else:
            window_hours = scrape_window_hours(mode)

        attempt_keys: list[str | None] = []
        if mode == "historical":
            attempt_keys.extend([creator.tiktok_username, f"{creator.tiktok_username}#retry1"])
        else:
            attempt_keys.append(creator.tiktok_username)
        if (
            settings.local_mode
            and settings.proxy_pool_local_env_fallback
            and settings.scrape_proxy_url
        ):
            attempt_keys.append(None)

        videos_data: list = []
        profile = None

        for idx, task_key in enumerate(attempt_keys):
            session_ctx = (
                proxy_pool.env_proxy_session()
                if task_key is None
                else proxy_pool.scrape_session(db, task_key=task_key)
            )
            async with session_ctx as session:
                batch, profile = await scraper.fetch_creator_videos(
                    creator.tiktok_username,
                    window_hours=window_hours,
                )
                if profile.follower_count:
                    creator.follower_count = profile.follower_count
                if profile.display_name:
                    creator.display_name = profile.display_name
                if profile.user_id and not creator.tiktok_user_id:
                    creator.tiktok_user_id = profile.user_id

                if batch:
                    videos_data = batch
                elif idx < len(attempt_keys) - 1:
                    session.mark_failure()
                    continue

                stats = ScrapeStats()
                stats.fetched_videos = len(videos_data)
                now = datetime.utcnow()

                for vd in videos_data:
                    if (
                        creator.tiktok_user_id
                        and vd.uploader_id
                        and vd.uploader_id != creator.tiktok_user_id
                    ):
                        stats.skipped_videos += 1
                        continue

                    result = await db.execute(select(Video).where(Video.video_id == vd.video_id))
                    video = result.scalar_one_or_none()

                    if video:
                        if mode == "historical":
                            stats.skipped_videos += 1
                            continue
                        if mode == "hot_ingest":
                            stats.skipped_videos += 1
                            continue
                        if mode == "hot_update":
                            if not should_update_for_hot_update(video, threshold.scrape_window_hours, now):
                                stats.skipped_videos += 1
                                continue
                        elif mode == "hot_refresh":
                            if not should_update_for_hot_refresh(video, now):
                                stats.skipped_videos += 1
                                continue
                        elif not should_update_existing_video(video, now):
                            stats.skipped_videos += 1
                            continue

                        video.view_count = vd.view_count
                        video.like_count = vd.like_count
                        video.share_count = vd.share_count
                        video.comment_count = vd.comment_count
                        if vd.source_username:
                            video.source_username = vd.source_username
                        if vd.video_url:
                            video.video_url = vd.video_url
                        video.updated_at = now
                        stats.updated_videos += 1
                    else:
                        if mode == "hot_update":
                            stats.skipped_videos += 1
                            continue
                        if mode in ("hot_ingest", "hot_update", "hot_refresh") and not should_ingest_new_for_hot(
                            vd.published_at, threshold.scrape_window_hours, now
                        ):
                            stats.skipped_videos += 1
                            continue
                        if mode == "historical" and not check_historical_viral(
                            vd.view_count, threshold.historical_view_threshold
                        ):
                            stats.skipped_videos += 1
                            continue

                        cover_bytes = await scraper.download_cover(vd.cover_url)
                        cover_local = None
                        cover_url = vd.cover_url
                        if cover_bytes:
                            cover_url, cover_local = store_cover(vd.video_id, cover_bytes)

                        video = Video(
                            creator_id=creator.id,
                            video_id=vd.video_id,
                            title=vd.title,
                            description=vd.description,
                            video_url=vd.video_url,
                            source_username=vd.source_username or None,
                            cover_url=cover_url,
                            cover_local_path=cover_local,
                            published_at=vd.published_at,
                            duration=vd.duration,
                            view_count=vd.view_count,
                            like_count=vd.like_count,
                            share_count=vd.share_count,
                            comment_count=vd.comment_count,
                        )
                        db.add(video)
                        await _flush_with_retry(db)
                        stats.new_videos += 1

                    db.add(VideoSnapshot(
                        video_id=video.video_id,
                        view_count=video.view_count,
                        like_count=video.like_count,
                        share_count=video.share_count,
                        comment_count=video.comment_count,
                        source=_snapshot_source(mode),
                    ))

                    await apply_video_classification(
                        db,
                        video,
                        threshold,
                        creator.tiktok_username,
                        scrape_interval_minutes=threshold.growth_window_minutes,
                    )

                    if video.is_historical_viral and not video.is_featured:
                        video.is_featured = True

                if mode == "historical":
                    if videos_data:
                        creator.historical_scraped_at = now
                        creator.last_scraped_at = now
                    else:
                        creator.historical_scraped_at = None
                elif mode == "hot_ingest":
                    creator.last_hot_ingest_at = now
                elif mode in ("hot_update", "hot_refresh"):
                    creator.last_hot_update_at = now
                elif mode == "daily":
                    creator.last_scraped_at = now

                if videos_data:
                    session.mark_success()
                elif mode == "daily" and profile and (profile.follower_count or profile.display_name):
                    session.mark_success()
                else:
                    session.mark_failure()

                await _flush_with_retry(db)
                await db.commit()

                return stats

        return ScrapeStats()

    async def scrape_group_creators(
        self, db: AsyncSession, group_id: int, mode: ScrapeMode = "daily", *, auto_historical: bool = False
    ) -> dict:
        result = await db.execute(
            select(MonitoredCreator)
            .options(selectinload(MonitoredCreator.group), selectinload(MonitoredCreator.collection))
            .where(MonitoredCreator.is_active == True, MonitoredCreator.group_id == group_id)
        )
        creators = result.scalars().all()
        stats = {"total": len(creators), "success": 0, "failed": 0, "new_videos": 0, "updated_videos": 0, "skipped_videos": 0}

        for creator in creators:
            retries = 0
            effective_mode = _effective_scrape_mode(creator, mode, auto_historical=auto_historical)
            while retries <= settings.scrape_max_retries:
                try:
                    result_stats = await self.scrape_creator(db, creator, mode=effective_mode)
                    stats["success"] += 1
                    stats["new_videos"] += result_stats.new_videos
                    stats["updated_videos"] += result_stats.updated_videos
                    stats["skipped_videos"] += result_stats.skipped_videos
                    break
                except Exception:
                    retries += 1
                    if retries <= settings.scrape_max_retries:
                        await asyncio.sleep(settings.scrape_retry_interval_minutes * 60)
                    else:
                        stats["failed"] += 1

        return stats

    async def scrape_all_creators(
        self, db: AsyncSession, mode: ScrapeMode = "daily", *, auto_historical: bool = False
    ) -> dict:
        if not settings.local_mode:
            raise RuntimeError(
                "混合部署禁止在 API/Beat 进程内串行 scrape_all_creators，请使用 scrape_all_creators_task"
            )
        result = await db.execute(
            select(MonitoredCreator)
            .options(selectinload(MonitoredCreator.group), selectinload(MonitoredCreator.collection))
            .where(MonitoredCreator.is_active == True)
        )
        creators = result.scalars().all()
        stats = {"total": len(creators), "success": 0, "failed": 0, "new_videos": 0, "updated_videos": 0, "skipped_videos": 0}

        for creator in creators:
            retries = 0
            effective_mode = _effective_scrape_mode(creator, mode, auto_historical=auto_historical)
            while retries <= settings.scrape_max_retries:
                try:
                    result_stats = await self.scrape_creator(db, creator, mode=effective_mode)
                    stats["success"] += 1
                    stats["new_videos"] += result_stats.new_videos
                    stats["updated_videos"] += result_stats.updated_videos
                    stats["skipped_videos"] += result_stats.skipped_videos
                    break
                except Exception:
                    retries += 1
                    if retries <= settings.scrape_max_retries:
                        await asyncio.sleep(settings.scrape_retry_interval_minutes * 60)
                    else:
                        stats["failed"] += 1

        return stats


collection_service = CollectionService()
