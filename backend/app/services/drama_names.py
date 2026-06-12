"""影视剧片名规范化（供 TMDB / 人工标注共用）。"""

import re

_UNKNOWN_NAMES = frozenset({
    "未知", "无", "none", "unknown", "n/a", "无法识别", "无法确定", "不详", "信息不足",
})

_INVALID_NAME_FRAGMENTS = (
    "无法识别", "无具体", "不能识别", "无法确定", "无明确", "未识别", "无信息",
    "信息不足", "no identifiable", "no title", "暂无",
)

_ANIMATION_TYPE_KEYWORDS = ("动画", "动漫", "卡通", "anime", "cartoon")

_SEASON_EPISODE_SUFFIX = re.compile(
    r"第\s*(\d+)\s*季(?:\s*第\s*(\d+)\s*集)?\s*$",
    re.IGNORECASE,
)

_EN_SEASON_EPISODE_SUFFIX = re.compile(
    r"(?:\s*[Ss]eason\s*\d+\s*(?:[Ee]pisode\s*\d+)?|\s*[Ss]\d+\s*[Ee]\d+)\s*$",
    re.IGNORECASE,
)

_SEASON_EPISODE_PATTERNS = (
    re.compile(r"第\s*(\d+)\s*季\s*第\s*(\d+)\s*集", re.IGNORECASE),
    re.compile(r"第\s*(\d+)\s*季(?!\s*第\s*\d+\s*集)", re.IGNORECASE),
    re.compile(r"[Ss](\d+)\s*[Ee](\d+)", re.IGNORECASE),
    re.compile(r"[Ss]eason\s*(\d+).*?[Ee]pisode\s*(\d+)", re.IGNORECASE),
)


def is_invalid_drama_name(name: str) -> bool:
    if not name:
        return True
    stripped = name.strip().strip("《》")
    lower = stripped.lower()
    if lower in _UNKNOWN_NAMES or stripped in _UNKNOWN_NAMES:
        return True
    return any(fragment in lower for fragment in _INVALID_NAME_FRAGMENTS)


def normalize_drama_name(name: str) -> str:
    name = (name or "").strip().strip("《》\"' ")
    if not name or is_invalid_drama_name(name):
        return ""
    if not name.startswith("《"):
        name = f"《{name}》"
    return name


def is_animation_drama_type(drama_type: str) -> bool:
    if not drama_type:
        return False
    lower = drama_type.strip().lower()
    return any(keyword in drama_type or keyword in lower for keyword in _ANIMATION_TYPE_KEYWORDS)


def enrich_animation_drama_type(drama_name: str, drama_type: str) -> str:
    """动画类：在类型字段追加基础片名（不含季/集），如 动画、恶搞之家。"""
    dtype = (drama_type or "").strip() or "未知"
    if not is_animation_drama_type(dtype):
        return dtype

    base = strip_season_episode_suffix(drama_name).strip().strip("《》\"' ")
    if not base or is_invalid_drama_name(base):
        return dtype

    parts: list[str] = []
    for part in re.split(r"[、,，/|]", dtype):
        part = part.strip()
        if not part or part == base:
            continue
        if part not in parts:
            parts.append(part)

    has_animation_tag = any(is_animation_drama_type(p) for p in parts) or is_animation_drama_type(dtype)
    if not has_animation_tag:
        parts.insert(0, "动画")

    if base not in parts:
        parts.append(base)

    return "、".join(parts)


def parse_positive_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _UNKNOWN_NAMES:
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def strip_season_episode_suffix(name: str) -> str:
    base = (name or "").strip().strip("《》")
    base = _SEASON_EPISODE_SUFFIX.sub("", base).strip()
    return _EN_SEASON_EPISODE_SUFFIX.sub("", base).strip()


_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100}


def _parse_chinese_int(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for ch in text:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            return None
    return total + current


def season_to_chinese_label(season: int) -> str:
    """22 → 二十二（用于匹配 Bangumi 中文季标题）。"""
    if season <= 0:
        return str(season)
    digits = "零一二三四五六七八九"
    if season < 10:
        return digits[season]
    if season < 20:
        ones = season % 10
        return "十" + (digits[ones] if ones else "")
    if season < 100:
        tens, ones = divmod(season, 10)
        head = digits[tens] if tens > 1 else ""
        tail = digits[ones] if ones else ""
        return f"{head}十{tail}"
    return str(season)


def parse_season_from_title(title: str) -> int | None:
    text = title or ""
    match = re.search(r"第\s*(\d+)\s*季", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"[Ss]eason\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"第([一二三四五六七八九十百千零]+)季", text)
    if match:
        return _parse_chinese_int(match.group(1))
    return None


def season_title_matches(target_season: int, title: str) -> bool | None:
    """True=季数吻合，False=季数冲突，None=标题未标明季数。"""
    if not target_season:
        return None
    text = title or ""
    parsed = parse_season_from_title(text)
    if parsed is not None:
        return parsed == target_season
    cn = season_to_chinese_label(target_season)
    if cn and f"第{cn}季" in text.replace(" ", ""):
        return True
    if str(target_season) in text and "季" in text:
        return True
    return None


def _extract_english_name(text: str) -> str:
    if not text:
        return ""
    for pattern in (
        r"英文名[：:]\s*([^\n；;]+)",
        r"English[：:]\s*([^\n；;]+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("《》\"' ")
    return ""


def bangumi_search_queries(
    name: str,
    *,
    english_name: str = "",
    analysis_reason: str = "",
) -> list[str]:
    """Bangumi 检索词：优先「片名 + 第N季」，去掉集数。"""
    raw = (name or "").strip().strip("《》\"' ")
    base = strip_season_episode_suffix(raw)
    season, _episode = extract_season_episode_from_text(raw)
    if season is None:
        season, _ = extract_season_episode_from_text(analysis_reason)

    en = (english_name or "").strip() or _extract_english_name(analysis_reason)

    queries: list[str] = []
    if base and season:
        queries.extend([
            f"{base}第{season}季",
            f"{base} 第{season}季",
        ])
        cn = season_to_chinese_label(season)
        if cn:
            queries.append(f"{base}第{cn}季")
            queries.append(f"{base} 第{cn}季")
        if en:
            queries.extend([
                f"{en} Season {season}",
                f"{en} 第{season}季",
            ])
    if base:
        queries.append(base)
    if en and en not in queries:
        queries.append(en)

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def bangumi_primary_search_query(name: str, *, english_name: str = "", analysis_reason: str = "") -> str:
    queries = bangumi_search_queries(name, english_name=english_name, analysis_reason=analysis_reason)
    return queries[0] if queries else strip_season_episode_suffix(name).strip().strip("《》\"' ")


def tmdb_search_query(name: str) -> str:
    """TMDB 检索用词：去掉季/集后缀，避免搜不到条目。"""
    return strip_season_episode_suffix(name)


def extract_season_episode_from_text(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    for pattern in _SEASON_EPISODE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        season = parse_positive_int(match.group(1))
        episode = parse_positive_int(match.group(2)) if match.lastindex and match.lastindex >= 2 else None
        if season is not None or episode is not None:
            return season, episode
    return None, None


def format_animation_drama_name(base_name: str, season: int | None, episode: int | None) -> str:
    base = strip_season_episode_suffix(base_name)
    if not base:
        return normalize_drama_name(base_name) or base_name

    suffix = ""
    if season is not None:
        suffix += f"第{season}季"
    if episode is not None:
        suffix += f"第{episode}集"
    if not suffix:
        return normalize_drama_name(base)

    return normalize_drama_name(f"{base}{suffix}")


def apply_animation_season_episode(
    drama_name: str,
    drama_type: str,
    season=None,
    episode=None,
    *,
    source_text: str = "",
) -> str:
    """动画类作品：将季/集信息并入片名，如《恶搞之家第22季第8集》。"""
    if not is_animation_drama_type(drama_type):
        return drama_name

    parsed_season = parse_positive_int(season)
    parsed_episode = parse_positive_int(episode)

    if parsed_season is None and parsed_episode is None and source_text:
        parsed_season, parsed_episode = extract_season_episode_from_text(source_text)

    if parsed_season is None and parsed_episode is None:
        name_season, name_episode = extract_season_episode_from_text(drama_name)
        if name_season is None and name_episode is None:
            return drama_name
        parsed_season, parsed_episode = name_season, name_episode

    base = strip_season_episode_suffix(drama_name) or drama_name.strip().strip("《》")
    return format_animation_drama_name(base, parsed_season, parsed_episode)
