from datetime import datetime, timedelta, date
from typing import Optional, Tuple

from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Video, VideoSnapshot, HistoricalViralArchive, DailyHotRecord
from app.services.thresholds import ThresholdConfig
from app.services.collection_policy import HOT_SNAPSHOT_SOURCES


def minutes_since_publish(published_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    if not published_at:
        return 1.0
    now = now or datetime.utcnow()
    return max((now - published_at).total_seconds() / 60.0, 1.0)


def calc_avg_view_velocity(view_count: int, published_at: Optional[datetime]) -> float:
    """平均流量增速：当前播放量 / 发布至今分钟数（播放/分钟）。"""
    views = int(view_count or 0)
    return round(views / minutes_since_publish(published_at), 2)


def _hot_snapshot_filter():
    return VideoSnapshot.source.in_(HOT_SNAPSHOT_SOURCES)


async def _hot_snapshot_count(db: AsyncSession, video_id: str) -> int:
    result = await db.execute(
        select(func.count(VideoSnapshot.id)).where(
            and_(VideoSnapshot.video_id == video_id, _hot_snapshot_filter())
        )
    )
    hot_count = result.scalar() or 0
    if hot_count > 1:
        return hot_count
    result = await db.execute(
        select(func.count(VideoSnapshot.id)).where(VideoSnapshot.video_id == video_id)
    )
    return result.scalar() or 0


def _snap_query(video_id: str, extra_filters, use_hot_only: bool):
    q = select(VideoSnapshot).where(and_(VideoSnapshot.video_id == video_id, *extra_filters))
    if use_hot_only:
        q = q.where(_hot_snapshot_filter())
    return q


async def calc_instant_view_velocity(
    db: AsyncSession,
    video: Video,
    window_minutes: int,
) -> float:
    """瞬时流量增速：以 B 线快照（hot_update / hot_ingest）为主；不足时回退全部快照。"""
    window = max(int(window_minutes or 1), 1)
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=window)

    total_snaps = await _hot_snapshot_count(db, video.video_id)
    if total_snaps <= 1:
        return 0.0

    hot_count_result = await db.execute(
        select(func.count(VideoSnapshot.id)).where(
            and_(VideoSnapshot.video_id == video.video_id, _hot_snapshot_filter())
        )
    )
    use_hot_only = (hot_count_result.scalar() or 0) > 1

    result = await db.execute(
        _snap_query(video.video_id, [VideoSnapshot.snapshot_at <= cutoff], use_hot_only)
        .order_by(VideoSnapshot.snapshot_at.desc())
        .limit(1)
    )
    baseline = result.scalar_one_or_none()
    if baseline and baseline.view_count is not None:
        delta = int(video.view_count or 0) - int(baseline.view_count or 0)
        return round(max(delta, 0) / window, 2)

    result = await db.execute(
        _snap_query(video.video_id, [VideoSnapshot.snapshot_at >= cutoff], use_hot_only)
        .order_by(VideoSnapshot.snapshot_at.asc())
        .limit(1)
    )
    baseline = result.scalar_one_or_none()
    if not baseline or baseline.view_count is None:
        return 0.0

    elapsed = max((now - baseline.snapshot_at).total_seconds() / 60.0, 1.0)
    delta = int(video.view_count or 0) - int(baseline.view_count or 0)
    return round(max(delta, 0) / elapsed, 2)


async def get_view_velocities(
    db: AsyncSession,
    video: Video,
    scrape_interval_minutes: int,
) -> Tuple[float, float]:
    avg_velocity = calc_avg_view_velocity(video.view_count or 0, video.published_at)
    instant_velocity = await calc_instant_view_velocity(db, video, scrape_interval_minutes)
    return avg_velocity, instant_velocity


async def get_growth_rates(
    db: AsyncSession, video: Video, window_minutes: int = 30
) -> Tuple[float, float]:
    """兼容旧接口：返回 (瞬时播放增速, 平均播放增速)，单位均为 播放/分钟。"""
    avg, instant = await get_view_velocities(db, video, window_minutes)
    return instant, avg


def is_daily_eligible(published_at: Optional[datetime], window_hours: int) -> bool:
    if not published_at:
        return True
    return published_at >= datetime.utcnow() - timedelta(hours=window_hours)


def check_historical_viral(view_count: int, threshold: int) -> bool:
    """功能1：历史爆款 — 仅看播放量绝对值，一旦达标永久归档。"""
    return view_count >= threshold


def check_daily_hot(
    avg_view_velocity: float,
    threshold: ThresholdConfig,
    published_at: Optional[datetime],
) -> bool:
    """功能2：当日热门 — 仅由平均流量增速（播放/分钟）控制，不设基础播放量门槛。"""
    if not is_daily_eligible(published_at, threshold.scrape_window_hours):
        return False
    return avg_view_velocity >= threshold.daily_hot_avg_growth_threshold


def resolve_video_category(video: Video) -> str:
    """展示分类：当日热门与历史爆款独立判定，可同时成立；列表筛选以 bool 字段为准。"""
    if video.is_daily_hot:
        return "daily_hot"
    if video.is_historical_viral:
        return "historical_viral"
    return "normal"


async def apply_video_classification(
    db: AsyncSession,
    video: Video,
    threshold: ThresholdConfig,
    creator_username: str = "",
    scrape_interval_minutes: int = 1440,
) -> dict:
    avg_velocity = calc_avg_view_velocity(video.view_count or 0, video.published_at)
    instant_velocity = await calc_instant_view_velocity(db, video, scrape_interval_minutes)
    video.avg_view_velocity = avg_velocity
    video.instant_view_velocity = instant_velocity

    result = {
        "avg_view_velocity": avg_velocity,
        "instant_view_velocity": instant_velocity,
        "marked_historical": False,
        "marked_daily_hot": False,
    }

    # 历史爆款：播放量绝对值达标（与当日热门并行判定，互不排斥）
    if check_historical_viral(video.view_count or 0, threshold.historical_view_threshold):
        if not video.is_historical_viral:
            video.is_historical_viral = True
            video.historical_viral_at = datetime.utcnow()
            result["marked_historical"] = True

            existing = await db.execute(
                select(HistoricalViralArchive).where(HistoricalViralArchive.video_id == video.id)
            )
            if not existing.scalar_one_or_none():
                db.add(
                    HistoricalViralArchive(
                        video_id=video.id,
                        video_platform_id=video.video_id,
                        title=video.title,
                        creator_username=creator_username,
                        content_type=video.content_type,
                        view_count=video.view_count,
                        like_count=video.like_count,
                        share_count=video.share_count,
                        comment_count=video.comment_count,
                        threshold_used=threshold.historical_view_threshold,
                        published_at=video.published_at,
                    )
                )

    # 当日热门：平均增速 + 热门窗口（与历史爆款并行判定，互不排斥）
    if check_daily_hot(avg_velocity, threshold, video.published_at):
        video.is_daily_hot = True
        video.daily_hot_at = datetime.utcnow()
        video.daily_hot_growth = instant_velocity
        result["marked_daily_hot"] = True

        today = date.today()
        hot_existing = await db.execute(
            select(DailyHotRecord).where(
                and_(DailyHotRecord.video_id == video.id, DailyHotRecord.hot_date == today)
            )
        )
        if not hot_existing.scalar_one_or_none():
            db.add(
                DailyHotRecord(
                    video_id=video.id,
                    hot_date=today,
                    view_count=video.view_count,
                    view_growth=instant_velocity,
                    avg_view_velocity=avg_velocity,
                    view_threshold_used=0,
                    growth_threshold_used=threshold.daily_hot_avg_growth_threshold,
                )
            )
    else:
        if video.is_daily_hot:
            today = date.today()
            await db.execute(
                delete(DailyHotRecord).where(
                    and_(DailyHotRecord.video_id == video.id, DailyHotRecord.hot_date == today)
                )
            )
        video.is_daily_hot = False

    video.category = resolve_video_category(video)

    video.traffic_grade = _calc_grade(video.view_count or 0, avg_velocity, instant_velocity, threshold)
    return result


def _calc_grade(
    view_count: int,
    avg_velocity: float,
    instant_velocity: float,
    t: ThresholdConfig,
) -> str:
    score = 0
    if view_count >= t.historical_view_threshold:
        score += 40
    elif avg_velocity >= t.daily_hot_avg_growth_threshold:
        score += 25
    if avg_velocity >= t.daily_hot_avg_growth_threshold:
        score += 25
    elif avg_velocity >= t.daily_hot_avg_growth_threshold / 2:
        score += 12
    if instant_velocity >= t.daily_hot_avg_growth_threshold:
        score += 35
    elif instant_velocity >= t.daily_hot_avg_growth_threshold / 2:
        score += 18
    if score >= 80:
        return "S"
    if score >= 60:
        return "A"
    if score >= 40:
        return "B"
    return "C"


async def sync_content_type_from_recognition(db: AsyncSession, video: Video, drama_type: Optional[str]):
    if drama_type and drama_type not in ("未知", "非影视内容"):
        video.content_type = drama_type


async def get_trend_data(db: AsyncSession, video_id: str, hours: int = 30) -> list:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(VideoSnapshot)
        .where(and_(VideoSnapshot.video_id == video_id, VideoSnapshot.snapshot_at >= cutoff))
        .order_by(VideoSnapshot.snapshot_at.asc())
    )
    return result.scalars().all()
