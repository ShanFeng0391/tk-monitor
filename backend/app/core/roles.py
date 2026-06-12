"""用户角色与权限判断。"""

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"

ALL_ROLES = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_USER)

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "超级管理员",
    ROLE_ADMIN: "管理员",
    ROLE_USER: "普通用户",
}


def normalize_role(role: str | None) -> str:
    if role in ALL_ROLES:
        return role
    return ROLE_USER


def is_reserved_super_admin(user) -> bool:
    """内置 admin 账号，唯一超级管理员。"""
    return getattr(user, "username", None) == "admin" and is_super_admin(user)


def can_assign_super_admin_role(username: str) -> bool:
    from app.config import get_settings
    return username == get_settings().admin_username


def is_super_admin(user) -> bool:
    return getattr(user, "role", None) == ROLE_SUPER_ADMIN


def is_tier_admin(user) -> bool:
    return getattr(user, "role", None) == ROLE_ADMIN


def is_user_manager(user) -> bool:
    return is_super_admin(user) or is_tier_admin(user)


def is_privileged_admin(user) -> bool:
    return is_super_admin(user)


def can_manage_all_creators(user) -> bool:
    return is_super_admin(user)


def can_create_managed_role(actor, target_role: str) -> bool:
    if target_role == ROLE_SUPER_ADMIN:
        return False
    if is_super_admin(actor):
        return target_role in (ROLE_ADMIN, ROLE_USER)
    if is_tier_admin(actor):
        return target_role in (ROLE_ADMIN, ROLE_USER)
    return False


def can_modify_user(actor, target) -> bool:
    if not is_super_admin(actor):
        return False
    if actor.id == target.id:
        return True
    if target.role == ROLE_SUPER_ADMIN:
        return False
    return True


def can_tier_admin_modify_user(actor, target) -> bool:
    if not is_tier_admin(actor):
        return False
    if target.role == ROLE_SUPER_ADMIN:
        return False
    return getattr(target, "created_by_id", None) == actor.id


def can_delete_user(actor, target) -> bool:
    if actor.id == target.id:
        return False
    if not is_super_admin(actor):
        return False
    if target.role == ROLE_SUPER_ADMIN:
        return False
    return True
