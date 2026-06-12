from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_super_admin
from app.database import get_db
from app.models import User
from app.schemas import AccessGateOut, AccessGateUpdate
from app.services import access_gate

router = APIRouter(prefix="/api/v1/admin/access-gate", tags=["access-gate"])


@router.get("", response_model=AccessGateOut)
async def get_access_gate_admin(
    _admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return AccessGateOut(**await access_gate.get_admin(db))


@router.put("", response_model=AccessGateOut)
async def update_access_gate(
    data: AccessGateUpdate,
    _admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await access_gate.set_gate(db, data.question, data.answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccessGateOut(**result)
