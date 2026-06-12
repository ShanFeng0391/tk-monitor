from datetime import datetime, timedelta
from typing import Optional

from app.config import get_settings
from app.models import Video
from app.services.runtime_settings import runtime

settings = get_settings()

HOT_SNAPSHOT_SOURCES = ("hot_update", "hot_ingest")


def video_age_days(published_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    if not published_at:
        return 0.0
    now = now or datetime.utcnow()
    return (now - published_at).total_seconds() / 86400


def video_age_hours(published_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    if not published_at:
        return 0.0
    now = now or datetime.utcnow()
    return (now - published_at).total_seconds() / 3600


def is_within_hot_window(
    published_at: Optional[datetime],
    window_hours: int,
    now: Optional[datetime] = None,
) -> bool:
    if not published_at:
        return True
    return video_age_hours(published_at, now) <= max(int(window_hours or 1), 1)


def should_update_existing_video(video: Video, now: Optional[datetime] = None) -> bool:
    """日常定点采集：10 天内视频每 N 天更新；超过 10 天不更新。"""
    now = now or datetime.utcnow()
    age_days = video_age_days(video.published_at, now)
    if age_days > runtime.int("recent_video_days"):
        return False
    last = video.updated_at or video.created_at or now
    since_update = (now - last).total_seconds() / 86400
    return since_update >= runtime.int("recent_video_update_days")


def should_update_for_hot_refresh(video: Video, now: Optional[datetime] = None) -> bool:
    """兼容旧 hot_refresh：近期窗口内视频每次任务都更新数据。"""
    now = now or datetime.utcnow()
    age_days = video_age_days(video.published_at, now)
    return age_days <= runtime.int("recent_video_days")


def should_ingest_new_for_hot(published_at: Optional[datetime], window_hours: int, now: Optional[datetime] = None) -> bool:
    """线 A：仅热门窗口内的新视频入库。"""
    return is_within_hot_window(published_at, window_hours, now)


def should_update_for_hot_update(
    video: Video,
    window_hours: int,
    now: Optional[datetime] = None,
) -> bool:
    """线 B：仅热门窗口内已有视频更新播放。"""
    return is_within_hot_window(video.published_at, window_hours, now)


def scrape_window_hours(mode: str) -> int:
    """历史采集返回 0 表示不限制发布时间，抓取博主全部视频后再按阈值筛选。"""
    if mode == "historical":
        return settings.historical_scrape_window_hours
    if mode in ("hot_ingest", "hot_update"):
        return settings.scrape_video_window_hours
    return runtime.int("recent_video_days") * 24 + 24


def hot_fetch_window_hours(threshold_scrape_window_hours: int) -> int:
    return max(int(threshold_scrape_window_hours or 1), 1)


def is_unlimited_scrape_window(window_hours: int) -> bool:
    return window_hours <= 0
