"""Bangumi 番组计划 API：动漫类元数据与海报。"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.drama_names import (
    bangumi_search_queries,
    extract_season_episode_from_text,
    season_title_matches,
    strip_season_episode_suffix,
)

settings = get_settings()
logger = logging.getLogger(__name__)

BGM_API = "https://api.bgm.tv"
BGM_WEB = "https://bgm.tv/subject"
_BGM_ID_RE = re.compile(r"bgm\.tv/subject/(\d+)", re.IGNORECASE)

# SubjectType: 2 = 动画 (Anime)
ANIME_SUBJECT_TYPES = (2,)


def _user_agent() -> str:
    ua = (settings.bangumi_user_agent or "").strip()
    if ua:
        return ua
    return "tiktok-monitor/1.0 (https://github.com/local/tiktok-monitor)"


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": _user_agent(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = (settings.bangumi_access_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def extract_bangumi_id(text: str) -> int | None:
    match = _BGM_ID_RE.search(text or "")
    return int(match.group(1)) if match else None


def bangumi_page_url(subject_id: int) -> str:
    return f"{BGM_WEB}/{subject_id}"


def poster_from_images(images: dict[str, Any] | None) -> str | None:
    if not images:
        return None
    for key in ("large", "common", "medium", "grid", "small"):
        url = images.get(key)
        if url:
            return str(url)
    return None


def _target_season(drama_name: str, analysis_reason: str = "") -> int | None:
    season, _ = extract_season_episode_from_text(drama_name)
    if season is None:
        season, _ = extract_season_episode_from_text(analysis_reason)
    return season


def _score_candidate(
    item: dict[str, Any],
    query: str,
    *,
    target_season: int | None = None,
) -> float:
    q = (query or "").strip().lower()
    if not q:
        return 0.0

    titles = [
        str(item.get("name_cn") or ""),
        str(item.get("name") or ""),
    ]
    best = 0.0
    for title in titles:
        t = title.strip().lower()
        if not t:
            continue
        if q == t:
            best = max(best, 100.0)
        elif q in t or t in q:
            best = max(best, 85.0)
        elif q.replace(" ", "") == t.replace(" ", ""):
            best = max(best, 80.0)

    if target_season:
        combined = " ".join(titles)
        match = season_title_matches(target_season, combined)
        if match is True:
            best += 60.0
        elif match is False:
            best -= 80.0

    rank = item.get("rank")
    if isinstance(rank, (int, float)) and rank > 0:
        best += max(0.0, 30.0 - min(float(rank), 30.0))
    score = item.get("score")
    if isinstance(score, (int, float)):
        best += float(score) * 0.5
    return best


def _format_tags(subject: dict[str, Any], limit: int = 4) -> str:
    tags = subject.get("tags") or []
    names: list[str] = []
    for tag in tags[:limit]:
        name = tag.get("name") if isinstance(tag, dict) else None
        if name and name not in names:
            names.append(str(name))
    if names:
        return "、".join(names)
    meta = subject.get("meta_tags") or []
    return "、".join(str(x) for x in meta[:limit] if x) or "动画"


def _format_date(subject: dict[str, Any]) -> str:
    date = subject.get("date") or subject.get("air_date") or ""
    return str(date)[:4] if date else ""


def _format_staff(subject: dict[str, Any], limit: int = 3) -> str:
    persons = subject.get("persons") or []
    names: list[str] = []
    for person in persons:
        if not isinstance(person, dict):
            continue
        name = person.get("name") or person.get("name_cn")
        if name and name not in names:
            names.append(str(name))
        if len(names) >= limit:
            break
    return "，".join(names)


async def search_anime_subjects(client: httpx.AsyncClient, keyword: str) -> list[dict[str, Any]]:
    resp = await client.post(
        f"{BGM_API}/v0/search/subjects",
        headers=_headers(),
        json={
            "keyword": keyword,
            "sort": "rank",
            "filter": {"type": list(ANIME_SUBJECT_TYPES)},
        },
        timeout=25.0,
    )
    resp.raise_for_status()
    return list(resp.json().get("data") or [])


async def fetch_subject(client: httpx.AsyncClient, subject_id: int) -> dict[str, Any]:
    resp = await client.get(
        f"{BGM_API}/v0/subjects/{subject_id}",
        headers=_headers(),
        timeout=25.0,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_poster_url(subject_id: int) -> str | None:
    if not settings.bangumi_enabled:
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            detail = await fetch_subject(client, subject_id)
            return poster_from_images(detail.get("images"))
    except Exception as exc:
        logger.warning("Bangumi poster fetch failed id=%s: %s", subject_id, exc)
        return None


async def _pick_subject_id(
    client: httpx.AsyncClient,
    queries: list[str],
    *,
    target_season: int | None = None,
) -> tuple[Optional[int], str]:
    best_id: Optional[int] = None
    best_score = 0.0
    best_title = ""
    best_query = ""
    seen_ids: set[int] = set()
    logs: list[str] = []

    for query in queries:
        if not query:
            continue
        try:
            results = await search_anime_subjects(client, query)
        except Exception as exc:
            logger.warning("Bangumi search failed query=%s: %s", query, exc)
            logs.append(f"{query}: error {exc}")
            continue

        for item in results[:12]:
            sid = int(item["id"])
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            score = _score_candidate(item, query, target_season=target_season)
            title = item.get("name_cn") or item.get("name") or ""
            if score > best_score:
                best_score = score
                best_id = sid
                best_title = title
                best_query = query

    if not best_id:
        return None, "; ".join(logs) if logs else "no results"

    if target_season and best_score >= 70:
        return best_id, f"search={best_query} season={target_season} score={best_score:.1f} title={best_title}"
    if best_score >= 55:
        return best_id, f"search={best_query} score={best_score:.1f} title={best_title}"
    if best_score >= 40:
        return best_id, f"search={best_query} fallback score={best_score:.1f} title={best_title}"
    return None, f"no confident match (best={best_score:.1f} query={best_query})"


async def lookup_anime_metadata(
    drama_name: str,
    *,
    prefer_chinese_name: Optional[str] = None,
    english_name: str = "",
    analysis_reason: str = "",
) -> tuple[Optional[dict[str, Any]], str]:
    """根据片名在 Bangumi 检索动画条目。返回 (result_dict | None, log_text)。"""
    if not settings.bangumi_enabled:
        return None, "Bangumi disabled"

    queries = bangumi_search_queries(
        drama_name,
        english_name=english_name,
        analysis_reason=analysis_reason,
    )
    if not queries:
        base = strip_season_episode_suffix(drama_name).strip().strip("《》")
        if not base:
            return None, "empty query"
        queries = [base]

    target_season = _target_season(drama_name, analysis_reason)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        subject_id, match_note = await _pick_subject_id(
            client,
            queries,
            target_season=target_season,
        )
        if not subject_id:
            return None, match_note

        detail = await fetch_subject(client, subject_id)
        display_cn = prefer_chinese_name or drama_name
        cn_title = detail.get("name_cn") or detail.get("name") or queries[0]

        result = {
            "drama_name": display_cn if display_cn else cn_title,
            "drama_type": _format_tags(detail),
            "english_name": detail.get("name") or "",
            "release_year": _format_date(detail),
            "actors": _format_staff(detail),
            "source": "bangumi",
            "metadata_source": "bangumi",
            "bangumi_id": subject_id,
            "tmdb_url": bangumi_page_url(subject_id),
            "poster_url": poster_from_images(detail.get("images")),
            "bangumi_title_cn": cn_title,
            "bangumi_title_jp": detail.get("name") or "",
        }

        log = (
            f"[source=bangumi subject_id={subject_id} {match_note}]\n"
            f"queries={queries}\n"
            f"title_cn={cn_title}\n"
            f"title_jp={detail.get('name')}\n"
            f"url={result['tmdb_url']}"
        )
        return result, log


async def lookup_with_queries(
    queries: list[str],
    *,
    prefer_name: str,
    english_name: str = "",
    analysis_reason: str = "",
) -> tuple[Optional[dict[str, Any]], str]:
    merged = bangumi_search_queries(
        prefer_name,
        english_name=english_name,
        analysis_reason=analysis_reason,
    )
    for q in queries:
        q = (q or "").strip().strip("《》")
        if q and q not in merged:
            merged.append(q)

    if not merged:
        return None, "all queries failed"

    target_season = _target_season(prefer_name)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        subject_id, match_note = await _pick_subject_id(
            client,
            merged,
            target_season=target_season,
        )
        if not subject_id:
            return None, match_note

        detail = await fetch_subject(client, subject_id)
        cn_title = detail.get("name_cn") or detail.get("name") or merged[0]
        result = {
            "drama_name": prefer_name or cn_title,
            "drama_type": _format_tags(detail),
            "english_name": detail.get("name") or "",
            "release_year": _format_date(detail),
            "actors": _format_staff(detail),
            "source": "bangumi",
            "metadata_source": "bangumi",
            "bangumi_id": subject_id,
            "tmdb_url": bangumi_page_url(subject_id),
            "poster_url": poster_from_images(detail.get("images")),
            "bangumi_title_cn": cn_title,
            "search_query": merged[0],
        }
        return result, match_note


async def resolve_bangumi_assets(
    drama_name: str,
    analysis_reason: str = "",
) -> tuple[str | None, str | None]:
    """返回 (poster_url, bangumi_page_url)。"""
    if not settings.bangumi_enabled:
        return None, None

    subject_id = extract_bangumi_id(analysis_reason)
    if subject_id:
        poster = await fetch_poster_url(subject_id)
        return poster, bangumi_page_url(subject_id)

    result, _ = await lookup_anime_metadata(
        drama_name,
        prefer_chinese_name=drama_name,
        analysis_reason=analysis_reason,
    )
    if not result:
        return None, None
    return result.get("poster_url"), result.get("tmdb_url")
