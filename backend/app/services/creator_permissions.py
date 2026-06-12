from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MonitoredCreator, User, UserCollection
from app.core.roles import is_super_admin, is_tier_admin


def is_admin(user: User) -> bool:
    return is_super_admin(user)


async def can_manage_creator(db: AsyncSession, user: User, creator: MonitoredCreator) -> bool:
    if is_super_admin(user):
        return True
    if creator.user_id == user.id:
        return True
    if is_tier_admin(user):
        owner = (await db.execute(select(User).where(User.id == creator.user_id))).scalar_one_or_none()
        return owner is not None and owner.created_by_id == user.id
    return False


async def get_creator_or_404(db: AsyncSession, creator_id: int) -> MonitoredCreator:
    result = await db.execute(select(MonitoredCreator).where(MonitoredCreator.id == creator_id))
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    return creator


async def get_manageable_creator(db: AsyncSession, creator_id: int, user: User) -> MonitoredCreator:
    creator = await get_creator_or_404(db, creator_id)
    if not await can_manage_creator(db, user, creator):
        raise HTTPException(status_code=403, detail="无权操作其他账号添加的博主")
    return creator


async def get_owned_collection_or_403(
    db: AsyncSession, collection_id: int, user: User
) -> UserCollection:
    result = await db.execute(select(UserCollection).where(UserCollection.id == collection_id))
    col = result.scalar_one_or_none()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not is_admin(user) and col.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该合集")
    return col
