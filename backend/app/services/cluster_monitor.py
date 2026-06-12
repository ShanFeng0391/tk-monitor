"""双计算节点（本地 + 轻量#2）集群状态、心跳与运维建议。"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ProxyEndpoint
from app.services.proxy_gateway import gateway_status
from app.services.proxy_pool import proxy_pool, mask_proxy_url

logger = logging.getLogger(__name__)
settings = get_settings()

HEARTBEAT_TTL_SECONDS = 120
HEARTBEAT_KEY_PREFIX = "cluster:node:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _redis_client():
    import redis

    return redis.from_url(settings.redis_url, decode_responses=True)


def _heartbeat_key(node_id: str) -> str:
    return f"{HEARTBEAT_KEY_PREFIX}{node_id}"


def _worker_node_from_hostname(hostname: str) -> str:
    name = (hostname or "").lower()
    if name.startswith("local@"):
        return "local"
    if name.startswith("cloud2@"):
        return "cloud2"
    if name.startswith("hybrid@"):
        return "local"
    return "unknown"


def _inspect_celery() -> dict[str, Any]:
    if settings.local_mode:
        return {"ping": {}, "stats": {}, "by_node": {}, "total_online": 0}
    try:
        from app.tasks.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=1.0)
        ping = inspector.ping() or {}
        stats = inspector.stats() or {}
        by_node: dict[str, int] = {"local": 0, "cloud2": 0, "unknown": 0}
        for hostname in ping.keys():
            node = _worker_node_from_hostname(hostname)
            by_node[node] = by_node.get(node, 0) + 1
        return {
            "ping": ping,
            "stats": stats,
            "by_node": by_node,
            "total_online": len(ping),
        }
    except Exception as exc:
        logger.warning("celery inspect failed: %s", exc)
        return {"ping": {}, "stats": {}, "by_node": {}, "total_online": 0, "error": str(exc)}


def _expected_workers(node_id: str) -> int:
    if node_id == "cloud2":
        return settings.cluster_expected_workers_cloud2
    if node_id == "local":
        return settings.cluster_expected_workers_local
    return settings.celery_worker_concurrency


def _node_label(node_id: str) -> str:
    if node_id == settings.compute_node_id:
        return settings.compute_node_label or node_id
    if node_id == "local":
        return settings.cluster_node_label_local
    if node_id == "cloud2":
        return settings.cluster_node_label_cloud2
    return node_id


async def _inspect_celery_async() -> dict[str, Any]:
    return await asyncio.to_thread(_inspect_celery)


def _peer_url_points_to_self(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return True
    try:
        local_hosts = {socket.gethostname().lower(), "127.0.0.1"}
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            local_hosts.add(info[4][0])
        return host in local_hosts
    except OSError:
        return False


async def publish_current_node_heartbeat() -> None:
    if settings.local_mode:
        return

    celery = await _inspect_celery_async()
    node_id = settings.compute_node_id or "local"
    my_workers = celery.get("by_node", {}).get(node_id, 0)
    gw = gateway_status()

    payload = {
        "node_id": node_id,
        "label": settings.compute_node_label or node_id,
        "hostname": socket.gethostname(),
        "roles": {
            "api": True,
            "beat": False,
            "worker_host": my_workers > 0,
            "singbox": bool(gw.get("running")),
        },
        "worker_online": my_workers,
        "worker_expected": _expected_workers(node_id),
        "worker_prefix": settings.celery_worker_node_prefix,
        "gateway_error": gw.get("last_error"),
        "updated_at": _utcnow().isoformat(),
    }

    try:
        client = _redis_client()
        client.setex(_heartbeat_key(node_id), HEARTBEAT_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logger.warning("cluster heartbeat write failed: %s", exc)


def _read_beat_heartbeat(node_id: str) -> bool:
    try:
        return bool(_redis_client().exists(f"cluster:beat:{node_id}"))
    except Exception:
        return False


def _read_node_heartbeat(node_id: str) -> Optional[dict]:
    try:
        raw = _redis_client().get(_heartbeat_key(node_id))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def _check_peer_api() -> dict:
    url = (settings.cluster_peer_api_url or "").strip().rstrip("/")
    if not url:
        return {"configured": False, "reachable": None, "detail": "未配置对端 API"}
    if _peer_url_points_to_self(url):
        return {
            "configured": True,
            "reachable": True,
            "url": url,
            "status": "healthy",
            "detail": "本节点 API（已跳过自连 HTTP 检测）",
        }
    health_url = f"{url}/api/v1/system/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "configured": True,
                    "reachable": True,
                    "url": url,
                    "status": data.get("status"),
                    "detail": "连通正常",
                }
            return {
                "configured": True,
                "reachable": False,
                "url": url,
                "detail": f"HTTP {resp.status_code}",
            }
    except Exception as exc:
        return {"configured": True, "reachable": False, "url": url, "detail": str(exc)[:200]}


def _worker_status(online: int, expected: int, node_online: bool) -> str:
    if not node_online:
        return "offline"
    if online <= 0:
        return "offline"
    if online >= max(1, int(expected * 0.6)):
        return "ok"
    return "low"


def _build_node_view(node_id: str, heartbeat: Optional[dict], celery: dict) -> dict:
    expected = _expected_workers(node_id)
    workers_from_celery = celery.get("by_node", {}).get(node_id, 0)
    workers_online = workers_from_celery
    if heartbeat and heartbeat.get("worker_online") is not None:
        workers_online = max(workers_online, int(heartbeat.get("worker_online") or 0))

    last_seen_sec: Optional[int] = None
    node_online = False
    roles = {"api": False, "beat": False, "worker_host": False, "singbox": False}
    gateway_error = None
    label = _node_label(node_id)

    if heartbeat:
        node_online = True
        label = heartbeat.get("label") or label
        roles = heartbeat.get("roles") or roles
        gateway_error = heartbeat.get("gateway_error")
        try:
            updated = datetime.fromisoformat(heartbeat.get("updated_at", ""))
            last_seen_sec = int((_utcnow() - updated).total_seconds())
            if last_seen_sec > HEARTBEAT_TTL_SECONDS:
                node_online = False
        except (TypeError, ValueError):
            pass

    if node_id == "cloud2":
        roles["beat"] = _read_beat_heartbeat("cloud2")

    beat_should_run = node_id == "cloud2"
    beat_online = bool(roles.get("beat")) if beat_should_run else True
    if beat_should_run and node_online and not roles.get("beat"):
        beat_online = False

    return {
        "node_id": node_id,
        "label": label,
        "online": node_online,
        "last_seen_seconds_ago": last_seen_sec,
        "roles": roles,
        "beat_should_run": beat_should_run,
        "beat_online": beat_online,
        "worker_expected": expected,
        "worker_online": workers_online,
        "worker_status": _worker_status(workers_online, expected, node_online),
        "singbox_running": bool(roles.get("singbox")),
        "gateway_error": gateway_error,
        "is_current_node": node_id == (settings.compute_node_id or "local"),
    }


async def _proxy_insights(db: AsyncSession, celery: dict[str, Any] | None = None) -> dict:
    rows = await proxy_pool.list_proxies(db)
    enabled = [r for r in rows if r.enabled]
    if celery is None:
        celery = await _inspect_celery_async()
    total_workers = max(1, int(celery.get("total_online") or 0))

    high_failure: list[dict] = []
    unhealthy_ids: list[int] = []
    for row in rows:
        success = row.success_count or 0
        fail = row.fail_count or 0
        total = success + fail
        rate = round(fail / total, 3) if total > 0 else 0.0
        item = {
            "id": row.id,
            "label": row.label or "",
            "masked_url": mask_proxy_url(row),
            "health_status": row.health_status or "unknown",
            "success_count": success,
            "fail_count": fail,
            "failure_rate": rate,
            "in_cooldown": proxy_pool.is_in_cooldown(row.id),
            "last_error": row.last_error,
        }
        is_bad = (
            row.health_status == "unhealthy"
            or proxy_pool.is_in_cooldown(row.id)
            or (fail >= 5 and rate >= 0.4)
            or (fail >= settings.proxy_pool_max_fail_streak)
        )
        if is_bad:
            high_failure.append(item)
        if row.health_status == "unhealthy" or (fail >= 10 and rate >= 0.5):
            unhealthy_ids.append(row.id)

    healthy_enabled = [r for r in enabled if r.health_status == "healthy" and not proxy_pool.is_in_cooldown(r.id)]
    suggested_min = max(8, (total_workers + 1) // 2)

    recommendations: list[str] = []
    if len(enabled) < suggested_min:
        recommendations.append(
            f"建议至少 {suggested_min} 条可用代理（当前启用 {len(enabled)} 条，在线 Worker 约 {total_workers} 个）。"
        )
    if len(healthy_enabled) < max(4, total_workers // 3):
        recommendations.append("健康代理偏少，采集失败率可能升高，请添加节点或修复不可用的代理。")
    if high_failure:
        recommendations.append(f"有 {len(high_failure)} 条代理失败率偏高或处于冷却，可考虑删除并更换。")
    if not recommendations:
        recommendations.append("代理池状态正常，请保持定期健康检查。")

    pool_stats = await proxy_pool.pool_stats(db)
    return {
        **pool_stats,
        "healthy_available": len(healthy_enabled),
        "suggested_min_proxies": suggested_min,
        "high_failure_proxies": sorted(high_failure, key=lambda x: x["failure_rate"], reverse=True),
        "prune_candidate_ids": unhealthy_ids,
        "recommendations": recommendations,
    }


async def get_cluster_status(db: AsyncSession) -> dict:
    celery = await _inspect_celery_async()
    peer = await _check_peer_api()

    db_status = "ok"
    redis_status = "ok"
    try:
        await db.execute(select(func.count()).select_from(ProxyEndpoint))
    except Exception:
        db_status = "error"
    try:
        _redis_client().ping()
    except Exception:
        redis_status = "error"

    nodes = [
        _build_node_view("local", _read_node_heartbeat("local"), celery),
        _build_node_view("cloud2", _read_node_heartbeat("cloud2"), celery),
    ]

    alerts: list[str] = []
    for node in nodes:
        if not node["online"]:
            alerts.append(f"【{node['label']}】未在线或心跳超时，请检查该机器上的 API/Worker 是否已启动。")
        elif node["worker_status"] == "low":
            alerts.append(
                f"【{node['label']}】Worker 数量偏低（{node['worker_online']}/{node['worker_expected']}），采集速度可能变慢。"
            )
        elif node["worker_status"] == "offline" and node["online"]:
            alerts.append(f"【{node['label']}】节点在线但未检测到 Worker，请检查 Celery 进程。")
        if node["beat_should_run"] and not node["beat_online"]:
            alerts.append(f"【{node['label']}】应运行 Beat 调度器但未检测到，定时采集将无法触发。")
        if not node["singbox_running"] and node["online"]:
            alerts.append(f"【{node['label']}】sing-box 网关未运行，vmess/vless 代理可能不可用。")

    if peer.get("configured") and peer.get("reachable") is False:
        alerts.append(f"无法访问对端 API（{peer.get('url')}）：{peer.get('detail')}")

    if db_status != "ok":
        alerts.append("数据库连接异常，请检查轻量#1 上 PostgreSQL。")
    if redis_status != "ok":
        alerts.append("Redis 连接异常，请检查轻量#1 上 Redis。")

    proxy_insights = await _proxy_insights(db, celery=celery)

    overall = "healthy"
    if db_status != "ok" or redis_status != "ok" or not any(n["online"] for n in nodes):
        overall = "critical"
    elif alerts:
        overall = "degraded"

    return {
        "overall_status": overall,
        "alerts": alerts,
        "current_node_id": settings.compute_node_id or "local",
        "current_node_label": settings.compute_node_label or "本机",
        "nodes": nodes,
        "celery": {
            "total_workers_online": celery.get("total_online", 0),
            "by_node": celery.get("by_node", {}),
            "error": celery.get("error"),
        },
        "data_layer": {"database": db_status, "redis": redis_status},
        "peer_api": peer,
        "proxy_pool": proxy_insights,
        "timestamp": _utcnow(),
    }


async def prune_proxies(db: AsyncSession, *, mode: str = "high_failure", ids: list[int] | None = None) -> dict:
    if ids:
        target_ids = ids
    elif mode == "unhealthy":
        rows = await proxy_pool.list_proxies(db)
        target_ids = [r.id for r in rows if r.health_status == "unhealthy"]
    else:
        insights = await _proxy_insights(db)
        target_ids = insights.get("prune_candidate_ids") or []

    deleted = 0
    for proxy_id in target_ids:
        row = await proxy_pool.get_proxy(db, proxy_id)
        if row:
            await proxy_pool.delete_proxy(db, row)
            deleted += 1
    return {"deleted": deleted, "ids": target_ids}
