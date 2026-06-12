"""登录/注册访问密钥（问题 + 答案）。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import SystemSetting

QUESTION_KEY = "access_gate_question"
ANSWER_HASH_KEY = "access_gate_answer_hash"


async def _get_value(db: AsyncSession, key: str) -> str | None:
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set_value(db: AsyncSession, key: str, value: str) -> None:
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


async def is_enabled(db: AsyncSession) -> bool:
    question = await _get_value(db, QUESTION_KEY)
    answer_hash = await _get_value(db, ANSWER_HASH_KEY)
    return bool(question and question.strip() and answer_hash)


async def get_public(db: AsyncSession) -> dict:
    question = await _get_value(db, QUESTION_KEY)
    enabled = await is_enabled(db)
    return {
        "enabled": enabled,
        "question": question.strip() if question else None,
    }


async def get_admin(db: AsyncSession) -> dict:
    public = await get_public(db)
    return {
        **public,
        "has_answer": bool(await _get_value(db, ANSWER_HASH_KEY)),
    }


async def verify(db: AsyncSession, answer: str | None) -> bool:
    if not await is_enabled(db):
        return True
    if not answer or not answer.strip():
        return False
    answer_hash = await _get_value(db, ANSWER_HASH_KEY)
    if not answer_hash:
        return False
    return verify_password(answer.strip(), answer_hash)


async def set_gate(db: AsyncSession, question: str, answer: str | None) -> dict:
    q = question.strip()
    if not q:
        raise ValueError("密钥问题不能为空")

    had_answer = bool(await _get_value(db, ANSWER_HASH_KEY))
    if answer is not None and answer.strip():
        await _set_value(db, ANSWER_HASH_KEY, hash_password(answer.strip()))
    elif not had_answer:
        raise ValueError("请设置密钥答案")

    await _set_value(db, QUESTION_KEY, q)
    await db.flush()
    return await get_admin(db)
