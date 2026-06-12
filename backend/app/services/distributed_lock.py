"""Redis 分布式锁（混合部署 / 多 Worker）。"""
from __future__ import annotations

import logging
from collections import defaultdict
import asyncio

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_group_update_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _redis_client():
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def hot_update_lock_key(group_id: int) -> str:
    return f"hot_update:lock:{group_id}"


def is_hot_update_running(group_id: int) -> bool:
    if settings.local_mode:
        return _group_update_locks[group_id].locked()
    try:
        return bool(_redis_client().exists(hot_update_lock_key(group_id)))
    except Exception as exc:
        logger.warning("Redis lock check failed group=%s: %s", group_id, exc)
        return False


def try_acquire_hot_update_lock(group_id: int, ttl_seconds: int = 7200) -> bool:
    if settings.local_mode:
        lock = _group_update_locks[group_id]
        if lock.locked():
            return False
        # 本地模式在 hot_refresh 里用 async with lock
        return True

    try:
        return bool(_redis_client().set(hot_update_lock_key(group_id), "1", nx=True, ex=ttl_seconds))
    except Exception as exc:
        logger.warning("Redis lock acquire failed group=%s: %s", group_id, exc)
        return False


def release_hot_update_lock(group_id: int) -> None:
    if settings.local_mode:
        return
    try:
        _redis_client().delete(hot_update_lock_key(group_id))
    except Exception as exc:
        logger.warning("Redis lock release failed group=%s: %s", group_id, exc)


def local_hot_update_lock(group_id: int) -> asyncio.Lock:
    return _group_update_locks[group_id]
