import re

from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MonitoredCreator

# @ 后：字母、数字、下划线、点，1~49 位
_CREATOR_USERNAME_RE = re.compile(r"^@[A-Za-z0-9_.]{1,49}$")
_PLAIN_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{1,49}$")
_TIKTOK_URL_RE = re.compile(r"tiktok\.com/@([A-Za-z0-9_.]{1,49})", re.I)
_AT_USERNAME_RE = re.compile(r"@([A-Za-z0-9_.]{1,49})\b")
_SKIP_PLAIN = {"none", "无", "未知", "null", "n/a"}


def format_creator_username(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="请输入博主用户名")
    if not value.startswith("@"):
        value = f"@{value}"
    if not _CREATOR_USERNAME_RE.match(value):
        raise HTTPException(status_code=400, detail="用户名格式不正确，示例：username 或 @username")
    return value


def validate_creator_username_format(raw: str) -> str:
    """校验并返回原始输入（保留 @ 前缀，供接口层继续处理）。"""
    return format_creator_username(raw)

def normalize_creator_username(raw: str) -> str:
    """去掉 @ 并规范化，用于入库与比对。"""
    formatted = format_creator_username(raw)
    return formatted[1:].strip().lower()


def _append_username(found: list[str], seen: set[str], username: str) -> None:
    token = (username or "").strip().lstrip("@")
    if not token or not _PLAIN_USERNAME_RE.match(token):
        return
    if token.lower() in _SKIP_PLAIN:
        return
    key = token.lower()
    if key in seen:
        return
    seen.add(key)
    found.append(f"@{token}")


def extract_usernames_from_text(text: str) -> list[str]:
    """从任意文本中提取 @username（去重、保序，可不带 @）。"""
    found: list[str] = []
    seen: set[str] = set()
    raw = text or ""

    for match in _TIKTOK_URL_RE.finditer(raw):
        _append_username(found, seen, match.group(1))

    for match in _AT_USERNAME_RE.finditer(raw):
        _append_username(found, seen, match.group(1))

    for chunk in re.split(r"[\n\r,;、]+", raw):
        token = chunk.strip().strip("\"'").lstrip("@")
        if not token:
            continue
        word = token.split()[0]
        _append_username(found, seen, word)

    return found


def normalize_username_list(raw_list: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_list:
        try:
            formatted = format_creator_username(raw)
        except HTTPException:
            continue
        key = formatted.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(formatted)
    return out


async def find_duplicate_creator(
    db: AsyncSession,
    username: str,
    *,
    tiktok_user_id: str | None = None,
) -> MonitoredCreator | None:
    normalized = username.lower()
    conditions = [func.lower(MonitoredCreator.tiktok_username) == normalized]
    if tiktok_user_id:
        conditions.append(MonitoredCreator.tiktok_user_id == tiktok_user_id)

    return (await db.execute(
        select(MonitoredCreator).where(or_(*conditions))
    )).scalar_one_or_none()


async def ensure_creator_not_duplicate(
    db: AsyncSession,
    username: str,
    *,
    tiktok_user_id: str | None = None,
) -> None:
    duplicate = await find_duplicate_creator(db, username, tiktok_user_id=tiktok_user_id)
    if not duplicate:
        return

    display = f"@{duplicate.tiktok_username}"
    raise HTTPException(status_code=400, detail=f"重复添加：博主 {display} 已在监控列表中")
