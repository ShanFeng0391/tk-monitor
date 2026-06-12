from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HistoricalViralArchive, VideoDramaRecognition, Video, MonitoredCreator
from app.config import get_settings
from app.services.group_helpers import archive_in_group, video_in_group

settings = get_settings()

INVALID_DRAMA_NAMES = {"未知", "非影视内容", "", None}
PERIOD_DAYS = 3


def _valid_drama(col):
    return and_(col.isnot(None), col.notin_(list(INVALID_DRAMA_NAMES - {None})))


from datetime import datetime, timedelta
from typing import Optional
import re
from collections import Counter

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import HistoricalViralArchive, VideoDramaRecognition, Video, MonitoredCreator
from app.config import get_settings
from app.services.group_helpers import archive_in_group, video_in_group

settings = get_settings()

INVALID_DRAMA_NAMES = {"未知", "非影视内容", "", None}
PERIOD_DAYS = 3
MIN_TYPE_SHARE_PERCENT = 2.0

INVALID_CONTENT_TYPES = frozenset({
    "未标注", "未知", "无法识别", "不详", "信息不足", "无", "none", "unknown", "n/a",
})
INVALID_CONTENT_FRAGMENTS = (
    "无法识别", "无明确", "未识别", "无信息", "信息不足", "不能识别", "无法确定", "无具体",
)
# 近3天爆款类型分布：泛化动漫标签不参与统计，只计具体片名（如 恶搞之家）
EXCLUDED_GENERIC_ANIMATION_TAGS = frozenset({"动画", "动漫"})


def _valid_drama(col):
    return and_(col.isnot(None), col.notin_(list(INVALID_DRAMA_NAMES - {None})))


def _is_invalid_content_type(token: str) -> bool:
    stripped = token.strip()
    if not stripped:
        return True
    lower = stripped.lower()
    if stripped in INVALID_CONTENT_TYPES or lower in INVALID_CONTENT_TYPES:
        return True
    return any(fragment in stripped for fragment in INVALID_CONTENT_FRAGMENTS)


def split_content_types(raw: Optional[str]) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[、，,/;；|]+", str(raw).strip())
    tokens: list[str] = []
    for part in parts:
        token = part.strip().strip("《》\"' ")
        if not token or _is_invalid_content_type(token):
            continue
        if token in EXCLUDED_GENERIC_ANIMATION_TAGS:
            continue
        tokens.append(token)
    return tokens


def _archive_type_source(arch: HistoricalViralArchive) -> Optional[str]:
    if arch.content_type and not _is_invalid_content_type(arch.content_type):
        return arch.content_type
    video = arch.video
    if not video:
        return None
    if video.content_type and not _is_invalid_content_type(video.content_type):
        return video.content_type
    rec = video.recognition
    if rec and rec.drama_type and not _is_invalid_content_type(rec.drama_type):
        return rec.drama_type
    return None


async def recent_viral_type_shares(
    db: AsyncSession, since: datetime, group_id: Optional[int] = None,
) -> list[dict]:
    query = (
        select(HistoricalViralArchive)
        .options(
            selectinload(HistoricalViralArchive.video).selectinload(Video.recognition),
        )
        .where(HistoricalViralArchive.archived_at >= since)
    )
    if group_id is not None:
        query = query.where(archive_in_group(group_id))

    archives = (await db.execute(query)).scalars().all()
    counter: Counter[str] = Counter()
    for arch in archives:
        raw = _archive_type_source(arch)
        if not raw:
            continue
        for token in split_content_types(raw):
            counter[token] += 1

    total = sum(counter.values())
    if not total:
        return []

    items = []
    for name, cnt in counter.most_common():
        percentage = round(cnt / total * 100, 1)
        if percentage < MIN_TYPE_SHARE_PERCENT:
            continue
        items.append({
            "content_type": name,
            "count": cnt,
            "percentage": percentage,
        })
    return items


async def multi_viral_dramas(
    db: AsyncSession, since: datetime, limit: int = 10, group_id: Optional[int] = None,
) -> list[dict]:
    query = (
        select(
            VideoDramaRecognition.drama_name,
            func.max(VideoDramaRecognition.drama_type).label("drama_type"),
            func.count(HistoricalViralArchive.id).label("viral_count"),
            func.max(HistoricalViralArchive.archived_at).label("latest_archived_at"),
            func.coalesce(func.sum(HistoricalViralArchive.view_count), 0).label("total_views"),
        )
        .join(VideoDramaRecognition, VideoDramaRecognition.video_id == HistoricalViralArchive.video_id)
        .where(
            HistoricalViralArchive.archived_at >= since,
            _valid_drama(VideoDramaRecognition.drama_name),
        )
    )
    if group_id is not None:
        query = query.where(archive_in_group(group_id))
    rows = (await db.execute(
        query.group_by(VideoDramaRecognition.drama_name)
        .having(func.count(HistoricalViralArchive.id) >= 2)
        .order_by(func.count(HistoricalViralArchive.id).desc(), func.sum(HistoricalViralArchive.view_count).desc())
        .limit(limit)
    )).all()

    return [
        {
            "drama_name": r.drama_name,
            "drama_type": r.drama_type,
            "viral_count": r.viral_count,
            "latest_archived_at": r.latest_archived_at,
            "total_views": int(r.total_views or 0),
        }
        for r in rows
    ]


async def periodic_viral_recommendations(
    db: AsyncSession, since: datetime, limit: int = 8, group_id: Optional[int] = None,
) -> list[dict]:
    """周期性爆款：历史曾爆、近3天未再爆、间隔进入下一周期窗口，且近期素材播放接近阈值。"""
    now = datetime.utcnow()
    threshold = settings.historical_view_threshold
    recent_cutoff = now - timedelta(days=14)

    history_query = (
        select(
            VideoDramaRecognition.drama_name,
            func.max(VideoDramaRecognition.drama_type).label("drama_type"),
            func.count(HistoricalViralArchive.id).label("historical_viral_count"),
            func.max(HistoricalViralArchive.archived_at).label("last_viral_at"),
        )
        .join(VideoDramaRecognition, VideoDramaRecognition.video_id == HistoricalViralArchive.video_id)
        .where(_valid_drama(VideoDramaRecognition.drama_name))
    )
    if group_id is not None:
        history_query = history_query.where(archive_in_group(group_id))
    history_rows = (await db.execute(
        history_query.group_by(VideoDramaRecognition.drama_name)
        .having(func.count(HistoricalViralArchive.id) >= 1)
    )).all()

    recommendations = []
    for row in history_rows:
        last_viral = row.last_viral_at
        if not last_viral or last_viral >= since:
            continue

        days_since = max((now - last_viral).days, 1)
        if days_since < 4 or days_since > 60:
            continue

        recent_query = (
            select(func.max(Video.view_count))
            .join(VideoDramaRecognition, VideoDramaRecognition.video_id == Video.id)
            .where(
                VideoDramaRecognition.drama_name == row.drama_name,
                Video.published_at.isnot(None),
                Video.published_at >= recent_cutoff,
            )
        )
        if group_id is not None:
            recent_query = recent_query.where(video_in_group(group_id))
        recent_max = (await db.execute(recent_query)).scalar() or 0

        if recent_max < threshold * 0.5:
            continue

        proximity = min(recent_max / threshold, 1.5)
        cycle_score = round(row.historical_viral_count * proximity * 100 / days_since, 2)
        recommendations.append({
            "drama_name": row.drama_name,
            "drama_type": row.drama_type,
            "historical_viral_count": row.historical_viral_count,
            "days_since_last_viral": days_since,
            "recent_max_views": int(recent_max),
            "cycle_score": cycle_score,
            "reason": f"距上次爆款 {days_since} 天，近期最高 {int(recent_max):,} 播放",
        })

    recommendations.sort(key=lambda x: x["cycle_score"], reverse=True)
    return recommendations[:limit]


async def build_viral_predictions(db: AsyncSession, group_id: Optional[int] = None) -> dict:
    since = datetime.utcnow() - timedelta(days=PERIOD_DAYS)
    return {
        "period_days": PERIOD_DAYS,
        "recent_type_shares": await recent_viral_type_shares(db, since, group_id),
        "periodic_recommendations": await periodic_viral_recommendations(db, since, group_id=group_id),
        "multi_viral_dramas": await multi_viral_dramas(db, since, group_id=group_id),
    }
