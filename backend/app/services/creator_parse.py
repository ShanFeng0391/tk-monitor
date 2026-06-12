"""从粘贴文本中提取 TikTok 博主用户名。"""

from app.config import get_settings
from app.services.creator_input import extract_usernames_from_text, normalize_username_list
from app.services.doubao import recognition_service
from app.services.runtime_settings import runtime

settings = get_settings()

CREATOR_PASTE_PROMPT = """从下列文本中提取 TikTok 博主账号。
只输出账号列表，每行一个 username（不需要加 @，仅含字母、数字、下划线和点）。
不要输出解释或其他文字。若没有账号，只输出 NONE。

文本：
{text}"""


def _usage_tokens(response) -> int:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0
    return int(getattr(usage, "total_tokens", 0) or 0)


async def parse_creator_paste(pasted_text: str) -> tuple[list[str], str, int]:
    text = (pasted_text or "").strip()
    if not text:
        return [], "empty", 0

    regex_users = normalize_username_list(extract_usernames_from_text(text))
    if regex_users and len(text) < 120:
        return regex_users, "regex", 0

    if not runtime.bool("doubao_enabled") or not recognition_service.client:
        return regex_users, "regex", 0

    response = recognition_service.client.chat.completions.create(
        model=settings.ark_model,
        messages=[{"role": "user", "content": CREATOR_PASTE_PROMPT.format(text=text[:8000])}],
        temperature=0.0,
        max_tokens=240,
    )
    content = (response.choices[0].message.content or "").strip()
    tokens = _usage_tokens(response)
    if content.upper() == "NONE" or not content:
        return regex_users, "regex", tokens

    ai_users = normalize_username_list(
        extract_usernames_from_text(content)
        + [line.strip() for line in content.splitlines() if line.strip()]
    )
    merged: list[str] = []
    seen: set[str] = set()
    for username in ai_users + regex_users:
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(username)
    source = "ai" if ai_users else "regex"
    return merged, source, tokens
