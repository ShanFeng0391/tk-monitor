"""识别分级 gate：决定是否在路径 A 之后触发路径 B（流式抽帧）。"""
import re
from typing import Optional

from app.config import get_settings

settings = get_settings()

_SPARSE_HINTS = (
    "无法识别",
    "无法判断",
    "无法确定",
    "不能识别",
    "未见",
    "无明显",
    "看不清",
    "难以辨认",
    "信息不足",
    "无法看清",
    "未出现",
    "不可见",
    "无明确",
    "没有明显",
    "缺乏",
    "unknown",
    "no identifiable",
)

_CLOSEUP_HINTS = ("特写", "局部", "仅见", "眼部", "眼睛", "局部特写", "大特写", "ecu")

_FIELD_KEYS = ("人物", "场景", "道具/动作", "画面基调")


def parse_structured_features(text: str) -> dict[str, str]:
    fields = {key: "" for key in _FIELD_KEYS}
    patterns = (
        ("人物", r"①\s*人物[：:]\s*(.+?)(?=②|$)"),
        ("场景", r"②\s*场景[：:]\s*(.+?)(?=③|$)"),
        ("道具/动作", r"③\s*道具[/／]?动作[：:]\s*(.+?)(?=④|$)"),
        ("画面基调", r"④\s*画面基调[：:]\s*(.+?)$"),
    )
    for key, pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            fields[key] = match.group(1).strip().replace("\n", " ")[:240]
    return fields


def _field_is_sparse(value: str) -> bool:
    text = (value or "").strip()
    if not text or len(text) < 4:
        return True
    lower = text.lower()
    return any(hint in text or hint in lower for hint in _SPARSE_HINTS)


def count_meaningful_dimensions(fields: dict[str, str]) -> int:
    return sum(1 for key in _FIELD_KEYS if not _field_is_sparse(fields.get(key, "")))


def should_trigger_stream_b(
    features: str,
    parsed: dict,
    *,
    confidence_threshold: Optional[float] = None,
) -> tuple[bool, str]:
    """
    返回 (是否触发 B, 原因码)。
    原因码写入 api_response 便于排查。
    """
    threshold = confidence_threshold if confidence_threshold is not None else settings.recognition_confidence_threshold
    fields = parse_structured_features(features)
    meaningful = count_meaningful_dimensions(fields)
    drama_name = parsed.get("drama_name", "未知")
    confidence = float(parsed.get("confidence") or 0)

    if drama_name in ("未知", "《信息不足》", "非影视内容"):
        return True, "match_unknown"

    if confidence < threshold:
        return True, "low_confidence"

    if meaningful < 2:
        return True, "sparse_features"

    person = fields.get("人物", "")
    if any(h in person for h in _CLOSEUP_HINTS) and meaningful < 3:
        return True, "close_up_sparse"

    scene = fields.get("场景", "")
    if _field_is_sparse(scene) and _field_is_sparse(fields.get("道具/动作", "")):
        return True, "missing_scene_and_prop"

    return False, ""
