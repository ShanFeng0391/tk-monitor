"""TMDB 片库查询：元数据补全主数据源。"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.drama_names import normalize_drama_name, tmdb_search_query

settings = get_settings()
logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_WEB = "https://www.themoviedb.org/movie"
TMDB_IMAGE = "https://image.tmdb.org/t/p"
_TMDB_ID_RE = re.compile(r"themoviedb\.org/movie/(\d+)")

_genre_map_zh: dict[int, str] = {}
_genre_lock = asyncio.Lock()


def _api_key() -> str:
    key = (settings.tmdb_api_key or "").strip()
    if not key:
        raise RuntimeError("TMDB_API_KEY 未配置")
    return key


def _normalize_query(name: str) -> str:
    cleaned = tmdb_search_query(name)
    return re.sub(r"\s+", " ", (cleaned or "").strip().strip("《》\"' "))


def poster_url(poster_path: str | None, size: str = "w500") -> str | None:
    if not poster_path:
        return None
    return f"{TMDB_IMAGE}/{size}{poster_path}"


def extract_tmdb_id(text: str) -> int | None:
    match = _TMDB_ID_RE.search(text or "")
    return int(match.group(1)) if match else None


async def fetch_poster_url(movie_id: int) -> str | None:
    if not settings.tmdb_api_key:
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                f"{TMDB_BASE}/movie/{movie_id}",
                params={"api_key": _api_key()},
                timeout=20.0,
            )
            resp.raise_for_status()
            return poster_url(resp.json().get("poster_path"))
    except Exception as exc:
        logger.warning("TMDB poster fetch failed id=%s: %s", movie_id, exc)
        return None


async def resolve_tmdb_assets(
    drama_name: str,
    analysis_reason: str = "",
) -> tuple[str | None, str | None]:
    """返回 (poster_url, tmdb_page_url)。"""
    if not settings.tmdb_api_key:
        return None, None

    movie_id = extract_tmdb_id(analysis_reason)
    if movie_id:
        poster = await fetch_poster_url(movie_id)
        return poster, f"{TMDB_WEB}/{movie_id}"

    query = _normalize_query(drama_name)
    if not query:
        return None, None

    result, _ = await lookup_movie_metadata(query, prefer_chinese_name=drama_name)
    if not result:
        return None, None
    return result.get("poster_url"), result.get("tmdb_url")


def _score_candidate(item: dict[str, Any], query: str) -> float:
    q = _normalize_query(query).lower()
    if not q:
        return 0.0

    titles = [
        item.get("title") or "",
        item.get("original_title") or "",
    ]
    alt = item.get("original_name") or item.get("name") or ""
    if alt:
        titles.append(alt)

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
        else:
            q_set = set(q)
            overlap = sum(1 for c in q_set if c in t)
            if overlap >= max(2, len(q_set) * 0.6):
                best = max(best, 55.0)

    popularity = float(item.get("popularity") or 0)
    vote = float(item.get("vote_count") or 0)
    best += min(popularity, 20) * 0.15 + min(vote, 5000) / 5000 * 5
    return best


async def _ensure_genres(client: httpx.AsyncClient) -> dict[int, str]:
    global _genre_map_zh
    if _genre_map_zh:
        return _genre_map_zh

    async with _genre_lock:
        if _genre_map_zh:
            return _genre_map_zh
        try:
            resp = await client.get(
                f"{TMDB_BASE}/genre/movie/list",
                params={"api_key": _api_key(), "language": "zh-CN"},
                timeout=20.0,
            )
            resp.raise_for_status()
            for item in resp.json().get("genres") or []:
                gid = item.get("id")
                name = item.get("name")
                if gid is not None and name:
                    _genre_map_zh[int(gid)] = str(name)
        except Exception as exc:
            logger.warning("TMDB genre list failed: %s", exc)
    return _genre_map_zh


async def _search_movies(client: httpx.AsyncClient, query: str, language: str) -> list[dict[str, Any]]:
    resp = await client.get(
        f"{TMDB_BASE}/search/movie",
        params={
            "api_key": _api_key(),
            "query": query,
            "language": language,
            "include_adult": "false",
        },
        timeout=25.0,
    )
    resp.raise_for_status()
    return list(resp.json().get("results") or [])


async def _pick_movie_id(client: httpx.AsyncClient, query: str) -> tuple[Optional[int], str]:
    """返回 (movie_id, 匹配说明)。"""
    best_id: Optional[int] = None
    best_score = 0.0
    best_title = ""

    for language in ("zh-CN", "en-US"):
        try:
            results = await _search_movies(client, query, language)
        except Exception as exc:
            logger.warning("TMDB search failed lang=%s query=%s: %s", language, query, exc)
            continue

        for item in results[:8]:
            score = _score_candidate(item, query)
            if score > best_score:
                best_score = score
                best_id = int(item["id"])
                best_title = item.get("title") or item.get("original_title") or ""

        if best_id and best_score >= 55:
            return best_id, f"search={query} lang={language} score={best_score:.1f} title={best_title}"

    if best_id and best_score >= 40:
        return best_id, f"search={query} fallback score={best_score:.1f} title={best_title}"
    return None, f"no match for query={query}"


async def _fetch_movie_bundle(client: httpx.AsyncClient, movie_id: int) -> dict[str, Any]:
    params = {"api_key": _api_key(), "append_to_response": "credits"}
    zh_resp, en_resp = await asyncio.gather(
        client.get(
            f"{TMDB_BASE}/movie/{movie_id}",
            params={**params, "language": "zh-CN"},
            timeout=25.0,
        ),
        client.get(
            f"{TMDB_BASE}/movie/{movie_id}",
            params={**params, "language": "en-US"},
            timeout=25.0,
        ),
    )
    zh_resp.raise_for_status()
    en_resp.raise_for_status()
    return {"zh": zh_resp.json(), "en": en_resp.json()}


def _format_genres(detail: dict[str, Any], genre_map: dict[int, str]) -> str:
    names: list[str] = []
    for g in detail.get("genres") or []:
        name = g.get("name")
        if not name and g.get("id") is not None:
            name = genre_map.get(int(g["id"]))
        if name and name not in names:
            names.append(str(name))
    return "、".join(names) if names else "未知"


def _format_cast(detail: dict[str, Any], limit: int = 3) -> str:
    credits = detail.get("credits") or {}
    cast = credits.get("cast") or []
    names = [c.get("name") for c in cast[:limit] if c.get("name")]
    return "，".join(names)


def _pick_english_name(zh_detail: dict[str, Any], en_detail: dict[str, Any]) -> str:
    original = (zh_detail.get("original_title") or en_detail.get("original_title") or "").strip()
    en_title = (en_detail.get("title") or "").strip()
    zh_title = (zh_detail.get("title") or "").strip()

    if original and original.lower() not in (zh_title.lower(), en_title.lower()):
        return original
    return en_title or original


async def lookup_movie_metadata(
    drama_name: str,
    *,
    prefer_chinese_name: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """
    根据片名在 TMDB 检索并返回标准元数据。
    返回 (result_dict | None, log_text)
    """
    query = _normalize_query(drama_name)
    if not query:
        return None, "empty query"

    if not settings.tmdb_api_key:
        return None, "TMDB_API_KEY not configured"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        await _ensure_genres(client)
        movie_id, match_note = await _pick_movie_id(client, query)
        if not movie_id:
            return None, match_note

        bundle = await _fetch_movie_bundle(client, movie_id)
        zh_detail = bundle["zh"]
        en_detail = bundle["en"]

        release = (zh_detail.get("release_date") or en_detail.get("release_date") or "")[:4]
        display_cn = prefer_chinese_name or drama_name
        normalized_cn = normalize_drama_name(display_cn) or normalize_drama_name(
            zh_detail.get("title") or query
        )

        result = {
            "drama_name": normalized_cn or normalize_drama_name(query) or "未知",
            "drama_type": _format_genres(zh_detail, _genre_map_zh),
            "english_name": _pick_english_name(zh_detail, en_detail),
            "release_year": release,
            "actors": _format_cast(zh_detail),
            "source": "tmdb",
            "tmdb_id": movie_id,
            "tmdb_url": f"{TMDB_WEB}/{movie_id}",
            "poster_url": poster_url(zh_detail.get("poster_path") or en_detail.get("poster_path")),
            "tmdb_title_zh": zh_detail.get("title") or "",
            "tmdb_title_en": en_detail.get("title") or "",
            "overview": (zh_detail.get("overview") or "")[:200],
        }

        log = (
            f"[source=tmdb movie_id={movie_id} {match_note}]\n"
            f"title_zh={result['tmdb_title_zh']}\n"
            f"title_en={result['tmdb_title_en']}\n"
            f"original={zh_detail.get('original_title')}\n"
            f"url={result['tmdb_url']}"
        )
        return result, log


async def lookup_with_queries(queries: list[str], *, prefer_name: str) -> tuple[Optional[dict[str, Any]], str]:
    logs: list[str] = []
    for q in queries:
        q = _normalize_query(q)
        if not q:
            continue
        result, log = await lookup_movie_metadata(q, prefer_chinese_name=prefer_name)
        logs.append(log)
        if result:
            result["search_query"] = q
            return result, "\n".join(logs)
    return None, "\n".join(logs) if logs else "all queries failed"
