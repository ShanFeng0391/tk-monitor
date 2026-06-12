from dataclasses import dataclass
from typing import Optional

from app.config import get_settings
from app.models import MonitorGroup, UserCollection
from app.services.runtime_settings import runtime

settings = get_settings()


@dataclass
class ThresholdConfig:
    historical_view_threshold: int
    daily_hot_avg_growth_threshold: float
    growth_window_minutes: int = 30
    scrape_window_hours: int = 30


def get_default_thresholds() -> ThresholdConfig:
    return ThresholdConfig(
        historical_view_threshold=runtime.int("historical_view_threshold"),
        daily_hot_avg_growth_threshold=runtime.float("daily_hot_avg_growth_threshold"),
        growth_window_minutes=runtime.int("growth_window_minutes"),
        scrape_window_hours=settings.scrape_video_window_hours,
    )


def thresholds_from_group(group: Optional[MonitorGroup]) -> ThresholdConfig:
    if not group:
        return get_default_thresholds()
    return ThresholdConfig(
        historical_view_threshold=group.historical_view_threshold,
        daily_hot_avg_growth_threshold=float(group.daily_hot_avg_growth_threshold or 50.0),
        growth_window_minutes=group.growth_window_minutes,
        scrape_window_hours=group.scrape_window_hours,
    )


def thresholds_from_collection(collection: Optional[UserCollection]) -> ThresholdConfig:
    if not collection:
        return get_default_thresholds()
    return ThresholdConfig(
        historical_view_threshold=collection.historical_view_threshold,
        daily_hot_avg_growth_threshold=float(collection.daily_hot_avg_growth_threshold or 50.0),
        growth_window_minutes=collection.growth_window_minutes,
        scrape_window_hours=collection.scrape_window_hours,
    )
