from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_super_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    ClusterStatusOut,
    DeployUpdateRequest,
    DeployUpdateStatusOut,
    DeployUpdateTriggerOut,
    ProxyPruneRequest,
    ProxyPruneResult,
)
from app.services.cluster_monitor import get_cluster_status, prune_proxies, publish_current_node_heartbeat
from app.services.deploy_update import get_deploy_update_status, trigger_deploy_update

router = APIRouter(prefix="/api/v1/admin/cluster", tags=["admin-cluster"])


@router.get("/status", response_model=ClusterStatusOut)
async def cluster_status(
    _: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    await publish_current_node_heartbeat()
    data = await get_cluster_status(db)
    return ClusterStatusOut(**data)


@router.post("/heartbeat")
async def cluster_heartbeat_ping(
    _: User = Depends(get_current_super_admin),
):
    await publish_current_node_heartbeat()
    return {"ok": True}


@router.get("/deploy-update", response_model=DeployUpdateStatusOut)
async def deploy_update_status(_: User = Depends(get_current_super_admin)):
    return DeployUpdateStatusOut(**get_deploy_update_status())


@router.post("/deploy-update", response_model=DeployUpdateTriggerOut)
async def deploy_update_trigger(
    body: DeployUpdateRequest,
    _: User = Depends(get_current_super_admin),
):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="请确认后再更新（confirm=true）")
    try:
        result = trigger_deploy_update(
            backend_only=body.backend_only,
            frontend_only=body.frontend_only,
            skip_git_pull=body.skip_git_pull,
            quick=body.quick,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeployUpdateTriggerOut(**result)
