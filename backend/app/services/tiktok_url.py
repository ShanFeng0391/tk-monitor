"""TikTok 视频链接构建与规范化。"""
from __future__ import annotations

import re

BASE_URL = "https://www.tiktok.com"
_VIDEO_URL_RE = re.compile(
    r"^https?://(?:www\.)?tiktok\.com/@(?P<user>[^/]+)/video/(?P<id>\d+)",
    re.IGNORECASE,
)


def normalize_username(username: str | None) -> str:
    return (username or "").strip().lstrip("@").strip()


def build_video_url(username: str | None, video_id: str | None) -> str:
    user = normalize_username(username)
    vid = str(video_id or "").strip()
    if not user or not vid:
        return ""
    return f"{BASE_URL}/@{user}/video/{vid}"


def resolve_video_url(
    *,
    video_id: str | None,
    creator_username: str | None = None,
    source_username: str | None = None,
    stored_url: str | None = None,
) -> str:
    """优先使用真实作者用户名，保证外链打开正确页面。"""
    preferred_user = normalize_username(source_username) or normalize_username(creator_username)
    built = build_video_url(preferred_user, video_id)
    stored = (stored_url or "").strip()

    if not stored:
        return built

    match = _VIDEO_URL_RE.match(stored)
    if not match:
        return built or stored

    stored_user = match.group("user")
    stored_id = match.group("id")
    if preferred_user and stored_user.lower() != preferred_user.lower():
        return build_video_url(preferred_user, stored_id) or stored
    if video_id and stored_id != str(video_id):
        return build_video_url(stored_user, video_id)
    return stored
