"""用户账号管理业务逻辑（TASK-001：用户管理权限）。

学生/教师账号由人员管理模块（person.py）建档时联动创建，
本模块负责账号层面的管理：查看、新建独立账号、重置密码、停用/启用。
"""

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.core.security import hash_password
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserStatus, UserType
from app.services.base import BaseCrudService

# user_type -> 默认角色（与 seed_rbac 保持一致）
_TYPE_ROLE = {
    UserType.STUDENT: RoleCode.STUDENT,
    UserType.TEACHER: RoleCode.TEACHER,
    UserType.ADMIN: RoleCode.ACADEMIC_ADMIN,
}


class UserService(BaseCrudService[User]):
    model = User
    search_fields = ("username", "real_name")
    unique_fields = ("username",)
    default_order = "id"
    entity_name = "用户"

    def base_stmt(self) -> Select:
        return select(User).options(selectinload(User.roles))

    def create_user(self, data: dict[str, Any]) -> User:
        username = data["username"]
        if self.db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none():
            raise Conflict(f"登录名已存在：{username}")

        role_codes = data.get("role_codes") or []
        if not role_codes:
            default = _TYPE_ROLE.get(data["user_type"])
            role_codes = [default] if default else []

        user = User(
            username=username,
            password_hash=hash_password(data["password"]),
            real_name=data["real_name"],
            user_type=data["user_type"],
            email=data.get("email"),
            phone=data.get("phone"),
        )
        self.db.add(user)
        self.db.flush()

        for code in role_codes:
            role = self.db.execute(
                select(Role).where(Role.code == code)
            ).scalar_one_or_none()
            if role is None:
                raise NotFound(f"角色不存在：{code}（请先执行 seed 脚本）")
            self.db.add(UserRole(user_id=user.id, role_id=role.id))

        self._commit()
        return user

    def reset_password(self, user_id: int, new_password: str) -> None:
        user = self.get_or_404(user_id)
        user.password_hash = hash_password(new_password)
        # 重置密码后解锁，允许重新登录
        user.failed_login_count = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        self._commit()

    def set_status(self, user_id: int, status: str) -> User:
        user = self.get_or_404(user_id)
        if status == UserStatus.DISABLED:
            user.status = UserStatus.DISABLED
        else:  # ACTIVE
            user.status = UserStatus.ACTIVE
            user.failed_login_count = 0
            user.locked_until = None
        self._commit()
        return user
