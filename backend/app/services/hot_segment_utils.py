"""热门更新 B 线：分时段周期工具（北京时间）。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: str) -> int:
    match = TIME_PATTERN.match((value or "").strip())
    if not match:
        raise ValueError(f"时间格式应为 HH:MM: {value!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


def format_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _segment_ranges(start_min: int, end_min: int) -> List[Tuple[int, int]]:
    if start_min == end_min:
        return [(0, 24 * 60)]
    if start_min < end_min:
        return [(start_min, end_min)]
    return [(start_min, 24 * 60), (0, end_min)]


def validate_segments_cover_24h(segments: Iterable[dict]) -> None:
    """校验分时段覆盖 24 小时且无重叠（北京时间）。"""
    items = sorted(segments, key=lambda s: parse_hhmm(s["start_time"]))
    if not items:
        raise ValueError("至少配置一个时段")

    covered = [False] * (24 * 60)
    for seg in items:
        start = parse_hhmm(seg["start_time"])
        end = parse_hhmm(seg["end_time"])
        interval = int(seg.get("interval_minutes") or 0)
        if interval < 5:
            raise ValueError("采集间隔不能小于 5 分钟")
        for a, b in _segment_ranges(start, end):
            for m in range(a, b):
                if covered[m]:
                    raise ValueError(f"时段 {seg['start_time']}-{seg['end_time']} 与已有配置重叠")
                covered[m] = True

    if not all(covered):
        first_gap = next(i for i, ok in enumerate(covered) if not ok)
        raise ValueError(f"时段未覆盖 24 小时，缺口起始于 {format_hhmm(first_gap)}（北京时间）")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def current_segment(segments: Iterable[dict], now: Optional[datetime] = None) -> Optional[dict]:
    now = now or beijing_now()
    minute = now.hour * 60 + now.minute
    for seg in segments:
        start = parse_hhmm(seg["start_time"])
        end = parse_hhmm(seg["end_time"])
        for a, b in _segment_ranges(start, end):
            if a <= minute < b:
                return seg
    return None


def default_segments_for_group(growth_window_minutes: int = 30) -> List[dict]:
    interval = max(int(growth_window_minutes or 30), 5)
    return [
        {"start_time": "08:00", "end_time": "22:00", "interval_minutes": interval, "sort_order": 0},
        {"start_time": "22:00", "end_time": "08:00", "interval_minutes": max(interval * 2, 60), "sort_order": 1},
    ]
