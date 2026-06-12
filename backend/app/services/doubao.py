"""影视剧元数据：人工标注为主，粘贴豆包识别结果 → AI 结构化提取，TMDB 仅作参考补充。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.runtime_settings import runtime
from app.models import Video, VideoDramaRecognition
from app.services import tmdb as tmdb_service
from app.services.drama_metadata_providers import resolve_drama_assets, supplement_reference, lookup_metadata_by_name
from app.services.drama_names import (
    apply_animation_season_episode,
    is_invalid_drama_name,
    normalize_drama_name,
    enrich_animation_drama_type,
)
from app.services.drama_stats import rebuild_drama_stats_for

settings = get_settings()

AI_SEARCH_HINT_PROMPT = """
用户输入的影视剧中文名或别名：{name}

任务：给出在 TMDB/IMDb 上最常用的英文片名检索词（单个名称）。
规则：只输出英文片名本身，不要解释；无法确定则输出 unknown
"""

DRAMA_LOOKUP_PROMPT = """
用户提供的影视剧名称：{name}

任务：根据该名称补全作品信息（使用你的影视知识库，不要编造不存在的作品）。

规则：
1. 中文名请使用通行译名；若用户输入已是标准中文名则原样使用。
2. 上映年份填首映年份（4 位数字）；不确定则 unknown。
3. 题材类型用简短中文标签（如 科幻、剧情、恐怖），多个用顿号分隔。
4. 主要演员列出 1~3 位，逗号分隔；不确定可留空。
5. 若完全无法对应任何已知作品，输出：信息不足|unknown|unknown|unknown|

严格只输出一行 pipe 格式，无任何其它文字：
中文名|英文名|上映年份|题材类型|主要演员
"""

DOUBAO_PASTE_PARSE_PROMPT = """
以下是一份豆包 AI 对图片/视频的影视剧识别结果（用户复制粘贴的长段文字）。请从中提取结构化信息，只使用文中明确出现的内容，不要编造。

规则：
1. 中文片名用文中《》内或明确写出的通行译名
2. 英文名取文中「英文名」或括号内的英文片名；无则 unknown
3. 上映年份取 4 位数字；无则 unknown
4. 题材类型用简短中文标签，多个用顿号分隔；无则 unknown
5. 主要演员列 1~3 位，逗号分隔；无则留空
6. 导演若文中有则填写；无则 unknown
7. 剧情简介取一句 60 字以内摘要；无则留空
8. 若为动画/动漫类，季数、集数单独填写数字；文中无则 unknown
9. 中文片名只填系列基础译名，不含「第X季第Y集」后缀
10. 若完全无法识别任何影视作品：信息不足|unknown|unknown|unknown|unknown|unknown|unknown|unknown

严格只输出一行 pipe 格式，无任何其它文字：
中文名|英文名|上映年份|题材类型|主要演员|导演|剧情摘要|季数|集数

--- 豆包识别原文 ---
{text}
"""


def _is_invalid_name(name: str) -> bool:
    return is_invalid_drama_name(name)


def _usage_tokens(response) -> int:
    if response.usage and response.usage.total_tokens:
        return int(response.usage.total_tokens)
    return 0


def _extract_pipe_line(content: str) -> str:
    for raw in content.splitlines():
        candidate = raw.strip().strip("`")
        if "|" in candidate and candidate.count("|") >= 3:
            return candidate
    return content.strip()


def parse_drama_lookup_line(content: str, *, fallback_name: str = "") -> dict:
    line = _extract_pipe_line(content)
    parts = [p.strip() for p in line.split("|")]
    while len(parts) < 5:
        parts.append("")

    cn, en, year, dtype, actors = parts[0], parts[1], parts[2], parts[3], parts[4]
    drama_name = normalize_drama_name(cn) or normalize_drama_name(fallback_name)

    if drama_name == "" and en and not _is_invalid_name(en):
        drama_name = normalize_drama_name(en)

    dtype_clean = dtype.strip() or "未知"
    if _is_invalid_name(dtype_clean):
        dtype_clean = "未知"

    year_clean = year.strip()
    if _is_invalid_name(year_clean):
        year_clean = ""

    return {
        "drama_name": drama_name or "未知",
        "drama_type": dtype_clean,
        "english_name": en if en and not _is_invalid_name(en) else "",
        "release_year": year_clean,
        "actors": actors.strip(),
        "raw_line": line,
    }


def parse_drama_paste_line(content: str, *, source_text: str = "") -> dict:
    line = _extract_pipe_line(content)
    parts = [p.strip() for p in line.split("|")]
    while len(parts) < 9:
        parts.append("")

    cn, en, year, dtype, actors, director, summary, season, episode = parts[:9]
    drama_name = normalize_drama_name(cn)

    if not drama_name and en and not _is_invalid_name(en):
        drama_name = normalize_drama_name(en)

    dtype_clean = dtype.strip() or "未知"
    if _is_invalid_name(dtype_clean):
        dtype_clean = "未知"

    year_clean = year.strip()
    if _is_invalid_name(year_clean):
        year_clean = ""

    director_clean = director.strip()
    if _is_invalid_name(director_clean):
        director_clean = ""

    summary_clean = summary.strip()
    if _is_invalid_name(summary_clean):
        summary_clean = ""

    drama_name = apply_animation_season_episode(
        drama_name or "未知",
        dtype_clean,
        season,
        episode,
        source_text=source_text,
    )

    dtype_clean = enrich_animation_drama_type(drama_name, dtype_clean)

    return {
        "drama_name": drama_name or "未知",
        "drama_type": dtype_clean,
        "english_name": en if en and not _is_invalid_name(en) else "",
        "release_year": year_clean,
        "actors": actors.strip(),
        "director": director_clean,
        "summary": summary_clean,
        "season": season.strip() if season else "",
        "episode": episode.strip() if episode else "",
        "raw_line": line,
    }


class DramaMetadataService:
    """AI 仅用于片名 → 元数据补全，不做图像识别。"""

    RECOGNITION_METHOD_MANUAL = "manual"
    RECOGNITION_METHOD_LOOKUP = "metadata_lookup"
    RECOGNITION_METHOD_TMDB = "tmdb"
    RECOGNITION_METHOD_BANGUMI = "bangumi"
    RECOGNITION_METHOD_AI_FALLBACK = "ai_fallback"
    RECOGNITION_METHOD_DOUBAO_PASTE = "doubao_paste"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None and runtime.bool("doubao_enabled"):
            cfg = get_settings()
            key = cfg.ark_api_key
            if key and key not in ("your-api-key-here", "your-ark-api-key-here"):
                try:
                    from volcenginesdkarkruntime import Ark
                    self._client = Ark(api_key=key, base_url=cfg.ark_base_url)
                except Exception:
                    pass
        return self._client

    def _ai_search_hint(self, drama_name: str) -> tuple[str, int]:
        """AI 辅助：中文片名 → 英文 TMDB 检索词。"""
        if not self.client:
            return "", 0
        prompt = AI_SEARCH_HINT_PROMPT.format(name=drama_name.strip())
        response = self.client.chat.completions.create(
            model=settings.ark_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=40,
        )
        content = (response.choices[0].message.content or "").strip()
        tokens = _usage_tokens(response)
        hint = content.splitlines()[0].strip().strip("\"' ")
        if not hint or hint.lower() == "unknown" or _is_invalid_name(hint):
            return "", tokens
        return hint, tokens

    def _lookup_drama_metadata_ai(self, raw_name: str) -> tuple[dict, str, int]:
        if not self.client:
            raise RuntimeError("豆包 API 未配置，且 TMDB 未命中，无法补全")

        prompt = DRAMA_LOOKUP_PROMPT.format(name=raw_name)
        response = self.client.chat.completions.create(
            model=settings.ark_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=120,
        )
        content = (response.choices[0].message.content or "").strip()
        tokens = _usage_tokens(response)
        parsed = parse_drama_lookup_line(content, fallback_name=raw_name)
        parsed["source"] = self.RECOGNITION_METHOD_AI_FALLBACK
        parsed["verified"] = False

        log = (
            f"[source=ai_fallback input={raw_name} tokens={tokens}]\n"
            f"=== AI 元数据补全（未验证，请人工核对）===\n{content}"
        )
        return parsed, log, tokens

    def _parse_doubao_paste_ai(self, pasted_text: str) -> tuple[dict, str, int]:
        if not self.client:
            raise RuntimeError("豆包 API 未配置，无法解析粘贴内容")

        text = (pasted_text or "").strip()
        if len(text) < 20:
            raise ValueError("粘贴内容过短，请复制完整的豆包识别结果")

        prompt = DOUBAO_PASTE_PARSE_PROMPT.format(text=text[:8000])
        response = self.client.chat.completions.create(
            model=settings.ark_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=280,
        )
        content = (response.choices[0].message.content or "").strip()
        tokens = _usage_tokens(response)
        parsed = parse_drama_paste_line(content, source_text=text)
        parsed["source"] = self.RECOGNITION_METHOD_DOUBAO_PASTE
        parsed["verified"] = parsed["drama_name"] not in ("未知", "《信息不足》")

        log = (
            f"[source=doubao_paste tokens={tokens}]\n"
            f"=== 豆包粘贴解析 ===\n{content}"
        )
        return parsed, log, tokens

    async def _external_reference_supplement(self, parsed: dict) -> tuple[dict, str]:
        """Bangumi（动漫）或 TMDB（其它）补充链接，不覆盖豆包/AI 主字段。"""
        return await supplement_reference(parsed)

    async def parse_doubao_paste(self, pasted_text: str) -> tuple[dict, str, int]:
        """
        粘贴豆包识别长文 → AI 结构化提取 → Bangumi/TMDB 参考补充（不覆盖主字段）。
        """
        if not runtime.bool("doubao_enabled"):
            raise RuntimeError("请在系统设置中启用豆包 AI")

        parsed, ai_log, tokens = self._parse_doubao_paste_ai(pasted_text)
        log_parts = [ai_log]

        if parsed.get("drama_name") in ("未知", "《信息不足》"):
            return parsed, "\n\n".join(log_parts), tokens

        parsed, ref_log = await self._external_reference_supplement(parsed)
        label = "Bangumi 参考" if parsed.get("metadata_source") == "bangumi" else "TMDB 参考"
        log_parts.append(f"=== {label} ===\n{ref_log}")
        return parsed, "\n\n".join(log_parts), tokens

    async def lookup_drama_metadata(self, drama_name: str) -> tuple[dict, str, int]:
        """
        动漫 → Bangumi 优先；其它 → TMDB 优先 → AI 辅助英文检索 → AI 全量兜底。
        返回 (parsed_dict, api_response_log, tokens_used)
        """
        raw_name = (drama_name or "").strip().strip("《》")
        if not raw_name:
            raise ValueError("请提供影视剧名称")

        tokens = 0
        log_parts: list[str] = []

        if settings.tmdb_api_key:
            tmdb_result, tmdb_log = await tmdb_service.lookup_movie_metadata(
                raw_name,
                prefer_chinese_name=raw_name,
            )
            log_parts.append(tmdb_log)
            if tmdb_result:
                tmdb_result["verified"] = True
                tmdb_result["metadata_source"] = "tmdb"
                return tmdb_result, "\n\n".join(log_parts), tokens

            if self.client and runtime.bool("doubao_enabled"):
                hint, used = self._ai_search_hint(raw_name)
                tokens += used
                if hint:
                    log_parts.append(f"=== AI 检索词辅助 ===\n{hint}")
                    tmdb_result2, tmdb_log2 = await tmdb_service.lookup_with_queries(
                        [hint, raw_name],
                        prefer_name=raw_name,
                    )
                    log_parts.append(tmdb_log2)
                    if tmdb_result2:
                        tmdb_result2["verified"] = True
                        tmdb_result2["metadata_source"] = "tmdb"
                        return tmdb_result2, "\n\n".join(log_parts), tokens

        if settings.bangumi_enabled:
            bg_result2, bg_log2 = await lookup_metadata_by_name(raw_name, drama_type="动画")
            log_parts.append(bg_log2)
            if bg_result2:
                return bg_result2, "\n\n".join(log_parts), tokens

        if runtime.bool("doubao_enabled") and self.client:
            parsed, ai_log, used = self._lookup_drama_metadata_ai(raw_name)
            tokens += used
            log_parts.append(ai_log)
            return parsed, "\n\n".join(log_parts), tokens

        if not settings.tmdb_api_key and not settings.bangumi_enabled:
            raise RuntimeError("请配置 TMDB_API_KEY 或启用 Bangumi，或开启豆包 API 作为兜底")
        raise RuntimeError(f"Bangumi/TMDB 与 AI 均未找到作品：{raw_name}")

    async def save_manual_recognition(
        self,
        db: AsyncSession,
        video: Video,
        rec: VideoDramaRecognition,
        *,
        drama_name: Optional[str] = None,
        drama_type: Optional[str] = None,
        actors: Optional[str] = None,
        analysis_reason: Optional[str] = None,
        user_id: Optional[int] = None,
        merge_lookup: Optional[dict] = None,
        prior_drama_name: Optional[str] = None,
    ) -> VideoDramaRecognition:
        """保存人工标注（可选合并 AI 补全字段）。"""
        old_name = prior_drama_name if prior_drama_name is not None else rec.drama_name

        if drama_name is not None:
            normalized = normalize_drama_name(drama_name)
            rec.drama_name = normalized or drama_name.strip()
        if drama_type is not None:
            rec.drama_type = drama_type.strip() or "未知"
            video.content_type = rec.drama_type
        if actors is not None:
            rec.actors = actors.strip()
        if analysis_reason is not None:
            rec.analysis_reason = analysis_reason.strip()

        if merge_lookup:
            if merge_lookup.get("drama_type") and merge_lookup["drama_type"] != "未知":
                if not rec.drama_type or rec.drama_type == "未知":
                    rec.drama_type = merge_lookup["drama_type"]
                    video.content_type = rec.drama_type
            if merge_lookup.get("actors") and not rec.actors:
                rec.actors = merge_lookup["actors"]
            bits = []
            if merge_lookup.get("english_name"):
                bits.append(f"英文名：{merge_lookup['english_name']}")
            if merge_lookup.get("release_year"):
                bits.append(f"年份：{merge_lookup['release_year']}")
            if bits:
                extra = "；".join(bits)
                rec.analysis_reason = f"{rec.analysis_reason}；{extra}" if rec.analysis_reason else extra

        rec.is_manual_override = True
        rec.manual_edited_by = user_id
        rec.manual_edited_at = datetime.utcnow()
        rec.recognition_method = self.RECOGNITION_METHOD_MANUAL
        rec.confidence = 100.0
        rec.status = "success"
        rec.completed_at = datetime.utcnow()
        rec.api_model = settings.ark_model

        if video.is_historical_viral:
            from app.models import HistoricalViralArchive
            arch = (await db.execute(
                select(HistoricalViralArchive).where(HistoricalViralArchive.video_id == video.id)
            )).scalar_one_or_none()
            if arch and video.content_type:
                arch.content_type = video.content_type

        new_name = rec.drama_name or ""
        old_valid = old_name and old_name not in ("未知", "非影视内容") and not _is_invalid_name(old_name)
        new_valid = new_name and new_name not in ("未知", "非影视内容") and not _is_invalid_name(new_name)
        if old_valid and old_name != new_name:
            await rebuild_drama_stats_for(db, old_name)
        if new_valid:
            await rebuild_drama_stats_for(db, new_name)

        await db.flush()
        return rec


recognition_service = DramaMetadataService()
