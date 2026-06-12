"""运行时系统设置：持久化到 system_settings 表，覆盖 .env 默认值。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SystemSetting

SETTINGS_KEYS = {
    "historical_view_threshold": "int",
    "daily_hot_avg_growth_threshold": "float",
    "growth_window_minutes": "int",
    "scrape_interval_minutes": "int",
    "recent_video_days": "int",
    "recent_video_update_days": "int",
    "doubao_enabled": "bool",
    "recognition_daily_budget": "float",
    "recognition_confidence_threshold": "float",
}

API_TO_INTERNAL = {
    "historical_view": "historical_view_threshold",
    "daily_hot_avg_growth": "daily_hot_avg_growth_threshold",
    "growth_window": "growth_window_minutes",
    "scrape_interval": "scrape_interval_minutes",
    "recent_video_days": "recent_video_days",
    "recent_video_update_days": "recent_video_update_days",
    "doubao_enabled": "doubao_enabled",
    "daily_budget": "recognition_daily_budget",
    "confidence": "recognition_confidence_threshold",
}

INTERNAL_TO_API = {v: k for k, v in API_TO_INTERNAL.items()}


def _coerce(key: str, value: Any) -> Any:
    kind = SETTINGS_KEYS[key]
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "on")
    return value


def _serialize(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _deserialize(key: str, raw: str | None) -> Any:
    if raw is None:
        return _default(key)
    kind = SETTINGS_KEYS[key]
    if kind == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    return raw


def _default(key: str) -> Any:
    settings = get_settings()
    if key == "daily_hot_avg_growth_threshold":
        return getattr(settings, "daily_hot_avg_growth_threshold", 50.0)
    if key == "daily_hot_growth_threshold":
        return settings.daily_hot_avg_growth_threshold
    if key == "daily_hot_view_threshold":
        return 0
    return getattr(settings, key, None)


class RuntimeSettings:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        if key in self._cache:
            return self._cache[key]
        if key == "daily_hot_growth_threshold" and "daily_hot_avg_growth_threshold" in self._cache:
            return self._cache["daily_hot_avg_growth_threshold"]
        if key == "daily_hot_avg_growth_threshold" and "daily_hot_growth_threshold" in self._cache:
            return self._cache["daily_hot_growth_threshold"]
        return _default(key)

    def int(self, key: str) -> int:
        return int(self.get(key))

    def float(self, key: str) -> float:
        return float(self.get(key))

    def bool(self, key: str) -> bool:
        if key == "doubao_enabled":
            return True
        value = self.get(key)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "on")

    async def load(self, db: AsyncSession) -> None:
        result = await db.execute(select(SystemSetting))
        self._cache = {}
        legacy_avg = None
        for row in result.scalars().all():
            if row.key == "daily_hot_growth_threshold" and row.key not in SETTINGS_KEYS:
                legacy_avg = _deserialize("daily_hot_avg_growth_threshold", row.value)
                continue
            if row.key in SETTINGS_KEYS:
                self._cache[row.key] = _deserialize(row.key, row.value)
            elif row.key == "daily_hot_growth_threshold":
                try:
                    legacy_avg = float(row.value)
                except (TypeError, ValueError):
                    pass
            elif row.key == "daily_hot_view_threshold":
                continue
        if legacy_avg is not None and "daily_hot_avg_growth_threshold" not in self._cache:
            self._cache["daily_hot_avg_growth_threshold"] = legacy_avg

    def to_api_dict(self) -> dict[str, Any]:
        return {
            api_key: self.get(internal_key)
            for api_key, internal_key in API_TO_INTERNAL.items()
        }

    async def save(self, db: AsyncSession, updates: dict[str, Any]) -> dict[str, Any]:
        for api_key, value in updates.items():
            if value is None:
                continue
            internal_key = API_TO_INTERNAL.get(api_key)
            if not internal_key:
                continue
            typed = _coerce(internal_key, value)
            self._cache[internal_key] = typed

            result = await db.execute(
                select(SystemSetting).where(SystemSetting.key == internal_key)
            )
            row = result.scalar_one_or_none()
            serialized = _serialize(typed)
            if row:
                row.value = serialized
            else:
                db.add(SystemSetting(key=internal_key, value=serialized))
        await db.commit()
        return self.to_api_dict()


runtime = RuntimeSettings()
