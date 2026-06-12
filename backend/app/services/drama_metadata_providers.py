"""影视剧外部元数据：动漫走 Bangumi，其余走 TMDB。"""
from __future__ import annotations

from typing import Optional

from app.services.drama_names import is_animation_drama_type
from app.services import bangumi as bangumi_service
from app.services import tmdb as tmdb_service


async def resolve_drama_assets(
    drama_name: str,
    drama_type: str = "",
    analysis_reason: str = "",
) -> tuple[str | None, str | None, Optional[str]]:
    """返回 (poster_url, page_url, metadata_source)。"""
    if is_animation_drama_type(drama_type):
        poster, url = await bangumi_service.resolve_bangumi_assets(drama_name, analysis_reason)
        if poster or url:
            return poster, url, "bangumi"

    poster, url = await tmdb_service.resolve_tmdb_assets(drama_name, analysis_reason)
    if poster or url:
        return poster, url, "tmdb"

    if not is_animation_drama_type(drama_type):
        return None, None, None

    poster, url = await bangumi_service.resolve_bangumi_assets(drama_name, analysis_reason)
    return poster, url, "bangumi" if (poster or url) else None


async def supplement_reference(parsed: dict) -> tuple[dict, str]:
    """粘贴/补全时补充外部参考链接（动漫 → Bangumi，其它 → TMDB）。"""
    drama_type = parsed.get("drama_type") or ""
    cn = (parsed.get("drama_name") or "").strip("《》")
    en = (parsed.get("english_name") or "").strip()
    queries: list[str] = []
    if cn and cn not in ("未知", "信息不足"):
        queries.append(cn)
    if en:
        queries.append(en)

    if not queries:
        return parsed, "no query for external reference"

    if is_animation_drama_type(drama_type):
        prefer = parsed.get("drama_name") or cn or en
        result, log = await bangumi_service.lookup_with_queries(
            queries,
            prefer_name=prefer,
            english_name=en,
            analysis_reason=parsed.get("summary") or "",
        )
        if not result:
            parsed["tmdb_ref_note"] = "未在 Bangumi 找到对照条目"
            return parsed, log

        parsed["bangumi_id"] = result.get("bangumi_id")
        parsed["tmdb_url"] = result.get("tmdb_url") or ""
        parsed["metadata_source"] = "bangumi"
        ref_name = result.get("bangumi_title_cn") or result.get("english_name") or ""
        ref_year = result.get("release_year") or ""
        parsed["tmdb_ref_note"] = f"Bangumi 参考：{ref_name} ({ref_year})".strip()
        return parsed, log

    from app.config import get_settings

    if not get_settings().tmdb_api_key:
        return parsed, "TMDB not configured"

    result, log = await tmdb_service.lookup_with_queries(queries, prefer_name=cn or en)
    if not result:
        parsed["tmdb_ref_note"] = "未在 TMDB 找到对照条目"
        return parsed, log

    parsed["tmdb_id"] = result.get("tmdb_id")
    parsed["tmdb_url"] = result.get("tmdb_url") or ""
    parsed["metadata_source"] = "tmdb"
    zh = result.get("tmdb_title_zh") or ""
    ref_year = result.get("release_year") or ""
    parsed["tmdb_ref_note"] = f"TMDB 参考：{zh or result.get('english_name') or ''} ({ref_year})".strip()
    return parsed, log


async def lookup_metadata_by_name(
    drama_name: str,
    *,
    drama_type: str = "",
) -> tuple[Optional[dict], str]:
    """按片名补全：动漫优先 Bangumi，其它优先 TMDB。"""
    raw_name = (drama_name or "").strip().strip("《》")
    if is_animation_drama_type(drama_type):
        result, log = await bangumi_service.lookup_anime_metadata(
            raw_name,
            prefer_chinese_name=raw_name,
        )
        if result:
            result["verified"] = True
            return result, log
        return None, log

    result, log = await tmdb_service.lookup_movie_metadata(raw_name, prefer_chinese_name=raw_name)
    if result:
        result["metadata_source"] = "tmdb"
        result["verified"] = True
        return result, log
    return None, log
