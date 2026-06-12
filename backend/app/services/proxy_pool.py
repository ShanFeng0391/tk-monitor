"""SOCKS5 代理池：本地内存调度，上云可扩展 Redis 共享状态。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional
from urllib.parse import quote, unquote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ProxyEndpoint

logger = logging.getLogger(__name__)
settings = get_settings()

_scrape_proxy: ContextVar[str | None] = ContextVar("scrape_proxy", default=None)

# 本地模式：进程内冷却与轮询
_local_rr_index = 0
_local_cooldown_until: dict[int, datetime] = {}


@dataclass
class ProxyHandle:
    id: int
    url: str


@dataclass
class ProxySession:
    handle: Optional[ProxyHandle]
    _success: bool = False

    def mark_success(self) -> None:
        self._success = True

    def mark_failure(self) -> None:
        self._success = False


def build_socks5_url(
    host: str,
    port: int,
    username: str = "",
    password: str = "",
) -> str:
    host = host.strip()
    if not host:
        raise ValueError("主机不能为空")
    if port < 1 or port > 65535:
        raise ValueError("端口无效")
    if username:
        user = quote(username, safe="")
        if password:
            return f"socks5://{user}:{quote(password, safe='')}@{host}:{port}"
        return f"socks5://{user}@{host}:{port}"
    return f"socks5://{host}:{port}"


def mask_proxy_url(row: ProxyEndpoint) -> str:
    protocol = (row.protocol or "socks5").lower()
    if protocol == "vmess":
        local = row.local_socks_port
        suffix = f" → socks5://127.0.0.1:{local}" if local else ""
        return f"vmess://***@{row.host}:{row.port}{suffix}"
    if protocol == "vless":
        local = row.local_socks_port
        suffix = f" → socks5://127.0.0.1:{local}" if local else ""
        return f"vless://***@{row.host}:{row.port}{suffix}"
    username = row.username or ""
    if username:
        return f"socks5://{username}:***@{row.host}:{row.port}"
    return f"socks5://{row.host}:{row.port}"


def _expand_socks_credentials(username: str, password: str) -> tuple[str, str]:
    """v2rayN 常把 user:pass 做 Base64 放在 socks5:// 的用户名段。"""
    if password or not username:
        return username, password
    import base64

    raw = username.strip()
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.b64decode(padded).decode("utf-8").strip()
    except Exception:
        try:
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8").strip()
        except Exception:
            return username, password
    if "@" in decoded and "://" not in decoded:
        auth, _, _rest = decoded.rpartition("@")
        if ":" in auth:
            user, pwd = auth.split(":", 1)
            if user and pwd:
                return user, pwd
    if ":" in decoded and "@" not in decoded:
        user, pwd = decoded.split(":", 1)
        if user and pwd:
            return user, pwd
    return username, password


def parse_socks5_url(url: str) -> tuple[str, int, str, str]:
    """解析 SOCKS5 链接；忽略 # 后的节点备注（如 #DE-145.79.93.56）。"""
    raw = url.strip()
    if not raw.lower().startswith("socks5://"):
        raise ValueError("仅支持 socks5:// 格式")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").strip()
    port = parsed.port
    if not host:
        raise ValueError("缺少主机")
    if port is None:
        raise ValueError("缺少端口")
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    username, password = _expand_socks_credentials(username, password)
    return host, port, username, password


def parse_socks5_label(url: str) -> str:
    """URL 中 # 后的片段可作为节点备注，例如 #DE-145.79.93.56。"""
    parsed = urlparse(url.strip())
    return unquote(parsed.fragment or "").strip()


def get_active_scrape_proxy() -> str | None:
    ctx = _scrape_proxy.get()
    if ctx:
        return ctx
    return settings.scrape_proxy_url or None


def _redis_client():
    import redis

    url = settings.redis_url
    if settings.proxy_pool_redis_db:
        if url.rstrip("/").split("/")[-1].isdigit():
            base = url.rsplit("/", 1)[0]
            url = f"{base}/{settings.proxy_pool_redis_db}"
    return redis.from_url(url, decode_responses=True)


def _use_redis() -> bool:
    return settings.proxy_pool_enabled and not settings.local_mode


def _cooldown_key(proxy_id: int) -> str:
    return f"proxy_pool:bad:{proxy_id}"


def _index_key() -> str:
    return "proxy_pool:rr_index"


class ProxyPoolService:
    async def list_proxies(self, db: AsyncSession) -> list[ProxyEndpoint]:
        result = await db.execute(
            select(ProxyEndpoint).order_by(ProxyEndpoint.id.asc())
        )
        return list(result.scalars().all())

    async def get_proxy(self, db: AsyncSession, proxy_id: int) -> ProxyEndpoint | None:
        return await db.get(ProxyEndpoint, proxy_id)

    async def create_proxy(
        self,
        db: AsyncSession,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        label: str = "",
        enabled: bool = True,
        protocol: str = "socks5",
        raw_uri: str | None = None,
    ) -> ProxyEndpoint:
        protocol = (protocol or "socks5").lower()
        if protocol == "socks5":
            build_socks5_url(host, port, username, password)
        elif protocol in ("vmess", "vless") and not raw_uri:
            raise ValueError("vmess / vless 需要分享链接")
        row = ProxyEndpoint(
            protocol=protocol,
            host=host.strip(),
            port=port,
            username=(username or "").strip(),
            password=password or "",
            raw_uri=raw_uri if protocol in ("vmess", "vless") else None,
            label=(label or "").strip(),
            enabled=enabled,
            health_status="unknown",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        if protocol in ("vmess", "vless"):
            from app.services.proxy_gateway import assign_local_port

            row.local_socks_port = assign_local_port(row.id)
            await db.commit()
            await db.refresh(row)
        await self._sync_gateway(db, row)
        return row

    async def update_proxy(
        self,
        db: AsyncSession,
        row: ProxyEndpoint,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        label: str | None = None,
        enabled: bool | None = None,
        protocol: str | None = None,
        raw_uri: str | None = None,
        clear_raw_uri: bool = False,
    ) -> ProxyEndpoint:
        gateway_changed = False
        if protocol is not None:
            row.protocol = protocol.lower()
            gateway_changed = True
        if clear_raw_uri:
            row.raw_uri = None
            row.local_socks_port = None
            gateway_changed = True
        if raw_uri is not None:
            row.raw_uri = raw_uri
            gateway_changed = True
            if not row.local_socks_port:
                from app.services.proxy_gateway import assign_local_port

                row.local_socks_port = assign_local_port(row.id)
        if host is not None:
            row.host = host.strip()
        if port is not None:
            row.port = port
        if username is not None:
            row.username = username.strip()
        if password is not None:
            row.password = password
        if label is not None:
            row.label = label.strip()
        if enabled is not None:
            row.enabled = enabled
        if (row.protocol or "socks5") == "socks5":
            build_socks5_url(row.host, row.port, row.username, row.password)
        row.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(row)
        if gateway_changed or row.protocol in ("vmess", "vless"):
            await self._sync_gateway(db, row)
        return row

    async def delete_proxy(self, db: AsyncSession, row: ProxyEndpoint) -> None:
        proxy_id = row.id
        was_gateway = row.protocol in ("vmess", "vless")
        await db.delete(row)
        await db.commit()
        self.clear_runtime_state(proxy_id)
        if was_gateway:
            await self._sync_gateway(db)

    def proxy_url(self, row: ProxyEndpoint) -> str:
        protocol = (row.protocol or "socks5").lower()
        if protocol in ("vmess", "vless"):
            port = row.local_socks_port or row.port
            return build_socks5_url("127.0.0.1", port)
        return build_socks5_url(row.host, row.port, row.username, row.password)

    async def _sync_gateway(
        self,
        db: AsyncSession,
        row: ProxyEndpoint | None = None,
    ) -> None:
        from app.services import proxy_gateway

        result = await proxy_gateway.sync_from_db(db)
        if row and row.protocol in ("vmess", "vless") and result.get("error"):
            row.last_error = str(result["error"])[:500]
            row.health_status = "unhealthy"
            row.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(row)

    def is_in_cooldown(self, proxy_id: int) -> bool:
        if _use_redis():
            try:
                r = _redis_client()
                return bool(r.exists(_cooldown_key(proxy_id)))
            except Exception as exc:
                logger.warning("Redis cooldown read failed: %s", exc)
        until = _local_cooldown_until.get(proxy_id)
        if until and until > datetime.utcnow():
            return True
        if until:
            _local_cooldown_until.pop(proxy_id, None)
        return False

    def clear_runtime_state(self, proxy_id: int) -> None:
        _local_cooldown_until.pop(proxy_id, None)
        if _use_redis():
            try:
                _redis_client().delete(_cooldown_key(proxy_id))
            except Exception:
                pass

    async def _available_rows(self, db: AsyncSession) -> list[ProxyEndpoint]:
        rows = await self.list_proxies(db)
        return [
            row
            for row in rows
            if row.enabled and row.health_status != "disabled" and not self.is_in_cooldown(row.id)
        ]

    async def acquire(self, db: AsyncSession, *, task_key: str = "") -> ProxyHandle | None:
        if not settings.proxy_pool_enabled:
            fallback = settings.scrape_proxy_url or None
            return ProxyHandle(id=0, url=fallback) if fallback else None

        available = await self._available_rows(db)
        if not available:
            fallback = settings.scrape_proxy_url or None
            return ProxyHandle(id=0, url=fallback) if fallback else None

        if task_key:
            idx = hash(task_key) % len(available)
            row = available[idx]
        else:
            global _local_rr_index
            if _use_redis():
                try:
                    r = _redis_client()
                    n = r.incr(_index_key())
                    idx = (n - 1) % len(available)
                except Exception:
                    idx = _local_rr_index % len(available)
                    _local_rr_index += 1
            else:
                idx = _local_rr_index % len(available)
                _local_rr_index += 1
            row = available[idx]

        return ProxyHandle(id=row.id, url=self.proxy_url(row))

    async def report_result(
        self,
        db: AsyncSession,
        proxy_id: int,
        *,
        success: bool,
        error: str = "",
    ) -> None:
        if proxy_id <= 0:
            return
        row = await db.get(ProxyEndpoint, proxy_id)
        if not row:
            return
        now = datetime.utcnow()
        if success:
            row.success_count = (row.success_count or 0) + 1
            row.fail_count = 0
            row.last_ok_at = now
            row.health_status = "healthy"
            row.last_error = None
            self.clear_runtime_state(proxy_id)
        else:
            row.fail_count = (row.fail_count or 0) + 1
            row.last_error = (error or "采集失败")[:500]
            if row.fail_count >= settings.proxy_pool_max_fail_streak:
                row.health_status = "unhealthy"
                self._set_cooldown(proxy_id)
        row.updated_at = now
        await db.commit()

    def _set_cooldown(self, proxy_id: int) -> None:
        ttl = max(60, settings.proxy_pool_bad_ttl_seconds)
        until = datetime.utcnow() + timedelta(seconds=ttl)
        _local_cooldown_until[proxy_id] = until
        if _use_redis():
            try:
                _redis_client().setex(_cooldown_key(proxy_id), ttl, "1")
            except Exception as exc:
                logger.warning("Redis cooldown write failed: %s", exc)

    async def check_health(
        self,
        db: AsyncSession,
        row: ProxyEndpoint,
        *,
        commit: bool = True,
    ) -> str:
        row.health_status = "checking"
        row.last_check_at = datetime.utcnow()
        if commit:
            await db.commit()

        url = self.proxy_url(row)
        status = "unhealthy"
        err_msg = ""
        try:
            async with httpx.AsyncClient(
                proxy=url,
                timeout=httpx.Timeout(20.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TikTokMonitor/1.0)",
                    "Accept": "text/html",
                },
            ) as client:
                resp = await client.get(settings.proxy_pool_health_url)
                if resp.status_code in (200, 301, 302, 403, 429):
                    status = "healthy"
                    row.last_ok_at = datetime.utcnow()
                    row.last_error = None
                    row.fail_count = 0
                else:
                    err_msg = f"HTTP {resp.status_code}"
        except Exception as exc:
            err_msg = str(exc)[:500]

        row.health_status = status
        row.last_check_at = datetime.utcnow()
        if status != "healthy":
            row.last_error = err_msg or "连接失败"
        if commit:
            await db.commit()
            await db.refresh(row)
        return status

    async def pool_stats(self, db: AsyncSession) -> dict:
        rows = await self.list_proxies(db)
        enabled = [r for r in rows if r.enabled]
        healthy = [r for r in enabled if r.health_status == "healthy"]
        unhealthy = [r for r in enabled if r.health_status == "unhealthy"]
        unknown = [r for r in enabled if r.health_status in ("unknown", "checking", "")]
        cooldown = [r for r in enabled if self.is_in_cooldown(r.id)]
        from app.services.proxy_gateway import gateway_status

        gw = gateway_status()
        gateway_rows = [
            r for r in rows if r.protocol in ("vmess", "vless") and r.local_socks_port
        ]
        return {
            "total": len(rows),
            "enabled": len(enabled),
            "healthy": len(healthy),
            "unhealthy": len(unhealthy),
            "unknown": len(unknown),
            "cooldown": len(cooldown),
            "backend": "redis" if _use_redis() else "memory",
            "pool_enabled": settings.proxy_pool_enabled,
            "fallback_url_configured": bool(settings.scrape_proxy_url),
            "gateway_running": gw.get("running", False),
            "gateway_nodes": len(gateway_rows),
            "gateway_error": gw.get("last_error"),
        }

    @asynccontextmanager
    async def env_proxy_session(self) -> AsyncIterator[ProxySession]:
        """本地开发：池内远程 SOCKS5 不可达时，回退到 SCRAPE_PROXY_URL（如 Clash 本地端口）。"""
        url = settings.scrape_proxy_url or None
        handle = ProxyHandle(id=0, url=url) if url else None
        token = _scrape_proxy.set(url)
        session = ProxySession(handle=handle)
        try:
            yield session
        finally:
            _scrape_proxy.reset(token)

    @asynccontextmanager
    async def scrape_session(
        self,
        db: AsyncSession,
        *,
        task_key: str = "",
    ) -> AsyncIterator[ProxySession]:
        handle = await self.acquire(db, task_key=task_key)
        proxy_url = handle.url if handle else None
        token = _scrape_proxy.set(proxy_url)
        session = ProxySession(handle=handle)
        try:
            yield session
        finally:
            _scrape_proxy.reset(token)
            if handle and handle.id > 0:
                await self.report_result(
                    db,
                    handle.id,
                    success=session._success,
                    error="" if session._success else "采集未成功",
                )


proxy_pool = ProxyPoolService()
