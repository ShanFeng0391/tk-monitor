from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_super_admin, get_current_user_manager, hash_password
from app.core.roles import (
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_USER,
    is_tier_admin,
    can_create_managed_role, can_modify_user, can_delete_user,
    can_assign_super_admin_role, can_tier_admin_modify_user,
)
from app.database import get_db
from app.models import User
from app.schemas import AdminUserCreate, AdminUserUpdate, UserOut
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])


def _resolve_create_role(data: AdminUserCreate, actor: User) -> str:
    if is_tier_admin(actor):
        return data.role if data.role in (ROLE_ADMIN, ROLE_USER) else ROLE_USER
    return data.role or ROLE_USER


async def _ensure_username_available(db: AsyncSession, username: str) -> None:
    existing = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")


async def _ensure_email_available(db: AsyncSession, email: str, exclude_user_id: int | None = None) -> None:
    query = select(User).where(User.email == email)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    existing = (await db.execute(query)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="邮箱已被使用")


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: AdminUserCreate,
    admin: User = Depends(get_current_user_manager),
    db: AsyncSession = Depends(get_db),
):
    role = _resolve_create_role(data, admin)

    if role == ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="不能创建超级管理员账号")

    if not can_create_managed_role(admin, role):
        raise HTTPException(status_code=403, detail="无权创建该角色账号")

    await _ensure_username_available(db, data.username)
    if data.email:
        await _ensure_email_available(db, data.email)

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role=role,
        is_active=data.is_active if data.is_active is not None else True,
        created_by_id=admin.id,
    )
    db.add(user)
    await db.flush()
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: AdminUserUpdate,
    admin: User = Depends(get_current_user_manager),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if is_tier_admin(admin):
        if not can_tier_admin_modify_user(admin, user):
            raise HTTPException(status_code=403, detail="无权修改该账号")
        fields = set(data.model_dump(exclude_unset=True))
        if fields - {"password", "role"}:
            raise HTTPException(status_code=400, detail="管理员仅可修改角色和密码")
        if data.role is not None and data.role != user.role:
            if not can_create_managed_role(admin, data.role):
                raise HTTPException(status_code=403, detail="无权设置该角色")
            user.role = data.role
        if data.password:
            user.password_hash = hash_password(data.password)
        await db.flush()
        return user

    if not can_modify_user(admin, user):
        raise HTTPException(status_code=403, detail="无权修改该账号")

    fields = data.model_dump(exclude_unset=True)
    if "email" in fields:
        if data.email:
            await _ensure_email_available(db, data.email, exclude_user_id=user.id)
            user.email = data.email
        else:
            user.email = None
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.role is not None and data.role != user.role:
        if data.role == ROLE_SUPER_ADMIN and not can_assign_super_admin_role(user.username):
            raise HTTPException(status_code=400, detail="仅 admin 账号可为超级管理员")
        if user.username == settings.admin_username and data.role != ROLE_SUPER_ADMIN:
            raise HTTPException(status_code=400, detail="不能修改 admin 账号的角色")
        if not can_create_managed_role(admin, data.role):
            raise HTTPException(status_code=403, detail="无权设置该角色")
        if user.role == ROLE_SUPER_ADMIN and user.username != settings.admin_username:
            raise HTTPException(status_code=400, detail="Cannot change super admin role")
        user.role = data.role

    await db.flush()
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not can_delete_user(admin, user):
        raise HTTPException(status_code=403, detail="无权删除该账号")
    await db.delete(user)
