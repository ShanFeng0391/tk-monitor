from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_super_admin
from app.database import get_db
from app.models import User, ProxyEndpoint
from app.schemas import ProxyCreate, ProxyUpdate, ProxyOut, ProxyPoolStatsOut, ProxyPruneRequest, ProxyPruneResult
from app.services.proxy_pool import proxy_pool, mask_proxy_url

router = APIRouter(prefix="/api/v1/admin/proxies", tags=["admin-proxies"])


def _to_out(row: ProxyEndpoint) -> ProxyOut:
    protocol = (row.protocol or "socks5").lower()
    success = row.success_count or 0
    fail = row.fail_count or 0
    total = success + fail
    failure_rate = round(fail / total, 3) if total > 0 else 0.0
    return ProxyOut(
        id=row.id,
        protocol=protocol,
        host=row.host,
        port=row.port,
        username=row.username or "",
        has_password=bool(row.password),
        label=row.label or "",
        enabled=row.enabled,
        health_status=row.health_status or "unknown",
        local_socks_port=row.local_socks_port,
        last_check_at=row.last_check_at,
        last_ok_at=row.last_ok_at,
        last_error=row.last_error,
        fail_count=fail,
        success_count=success,
        failure_rate=failure_rate,
        masked_url=mask_proxy_url(row),
        in_cooldown=proxy_pool.is_in_cooldown(row.id),
        created_at=row.created_at or datetime.utcnow(),
        updated_at=row.updated_at or datetime.utcnow(),
    )


@router.get("/stats", response_model=ProxyPoolStatsOut)
async def proxy_pool_stats(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.cluster_monitor import _proxy_insights

    data = await _proxy_insights(db)
    return ProxyPoolStatsOut(**{k: data[k] for k in ProxyPoolStatsOut.model_fields if k in data})


@router.get("", response_model=list[ProxyOut])
async def list_proxies(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await proxy_pool.list_proxies(db)
    return [_to_out(row) for row in rows]


@router.post("", response_model=ProxyOut, status_code=201)
async def create_proxy(
    data: ProxyCreate,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await proxy_pool.create_proxy(
            db,
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
            label=data.label,
            enabled=data.enabled,
            protocol=data.protocol,
            raw_uri=data.raw_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(row)


@router.put("/{proxy_id}", response_model=ProxyOut)
async def update_proxy(
    proxy_id: int,
    data: ProxyUpdate,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await proxy_pool.get_proxy(db, proxy_id)
    if not row:
        raise HTTPException(status_code=404, detail="代理不存在")
    try:
        clear_raw = data.protocol == "socks5" and data.share_uri
        row = await proxy_pool.update_proxy(
            db,
            row,
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
            label=data.label,
            enabled=data.enabled,
            protocol=data.protocol,
            raw_uri=data.raw_uri,
            clear_raw_uri=clear_raw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(row)


@router.delete("/{proxy_id}", status_code=204)
async def delete_proxy(
    proxy_id: int,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await proxy_pool.get_proxy(db, proxy_id)
    if not row:
        raise HTTPException(status_code=404, detail="代理不存在")
    await proxy_pool.delete_proxy(db, row)


@router.post("/reload-gateway")
async def reload_gateway(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services import proxy_gateway

    result = await proxy_gateway.sync_from_db(db)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{proxy_id}/check", response_model=ProxyOut)
async def check_proxy(
    proxy_id: int,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await proxy_pool.get_proxy(db, proxy_id)
    if not row:
        raise HTTPException(status_code=404, detail="代理不存在")
    await proxy_pool.check_health(db, row)
    return _to_out(row)


@router.post("/check-all", response_model=list[ProxyOut])
async def check_all_proxies(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await proxy_pool.list_proxies(db)
    results: list[ProxyOut] = []
    for row in rows:
        if not row.enabled:
            results.append(_to_out(row))
            continue
        await proxy_pool.check_health(db, row)
        refreshed = await proxy_pool.get_proxy(db, row.id)
        if refreshed:
            results.append(_to_out(refreshed))
    return results


@router.post("/prune", response_model=ProxyPruneResult)
async def prune_proxies_endpoint(
    body: ProxyPruneRequest,
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.cluster_monitor import prune_proxies

    result = await prune_proxies(db, mode=body.mode, ids=body.ids or None)
    return ProxyPruneResult(**result)
