"""用户账号管理业务逻辑（TASK-001：用户管理权限）。

学生/教师账号由人员管理模块（person.py）建档时联动创建，
本模块负责账号层面的管理：查看、新建独立账号、重置密码、停用/启用。

管理员身份（本次新增）以 **角色** 为准，而不是 user_type：
  - 拥有 ``roles.ACADEMIC_ADMIN`` 角色即为管理员（权限由 user_roles 解析）；
  - ``user_type`` 只表示账号的身份类别（TEACHER/STUDENT/ADMIN），
    被大量业务接口用于判断教师/学生身份，**授予管理员权限时不得改写**，
    否则教师将失去自己的教学班、课表与成绩录入能力。
  - ``user_roles`` 本就是多对多（含 (user_id, role_id) 唯一约束），
    因此「教师兼任管理员」无需新增表或迁移。
"""

from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.core.security import hash_password
from app.models.misc import OperationLog
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserStatus, UserType
from app.services.base import BaseCrudService

# user_type -> 默认角色（与 seed_rbac 保持一致）
_TYPE_ROLE = {
    UserType.STUDENT: RoleCode.STUDENT,
    UserType.TEACHER: RoleCode.TEACHER,
    UserType.ADMIN: RoleCode.ACADEMIC_ADMIN,
}

# 管理员角色：唯一判定依据
ADMIN_ROLE = RoleCode.ACADEMIC_ADMIN


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

    def set_status(
        self, user_id: int, status: str, operator: User | None = None
    ) -> User:
        user = self.get_or_404(user_id)
        if status == UserStatus.DISABLED:
            # 防止误操作导致系统无人可管理
            if operator is not None and operator.id == user.id:
                raise Conflict("不能停用当前登录账号自己，请由其他管理员操作")
            self._guard_last_active_admin(user, "停用")
            user.status = UserStatus.DISABLED
        else:  # ACTIVE
            user.status = UserStatus.ACTIVE
            user.failed_login_count = 0
            user.locked_until = None
        # 管理员账号的状态变更留痕（普通账号不记录，避免日志噪声）
        if self.is_admin(user):
            self._log(
                operator,
                "ADMIN_ENABLE" if status == UserStatus.ACTIVE else "ADMIN_DISABLE",
                user,
                f"{'启用' if status == UserStatus.ACTIVE else '停用'}"
                f"管理员账号 {user.real_name}（{user.username}）",
            )
        self._commit()
        return user

    # =========================== 管理员管理 ===========================
    # 判定依据统一为「是否持有 ACADEMIC_ADMIN 角色」（见模块 docstring）

    @staticmethod
    def _admin_role(db: Session) -> Role:
        role = db.execute(
            select(Role).where(Role.code == ADMIN_ROLE)
        ).scalar_one_or_none()
        if role is None:
            raise NotFound(f"角色不存在：{ADMIN_ROLE}（请先执行 seed_rbac 脚本）")
        return role

    def is_admin(self, user: User) -> bool:
        return any(r.code == ADMIN_ROLE for r in user.roles)

    def list_admins(self) -> list[User]:
        """所有管理员账号（含教师兼任），按账号类别与登录名排序。"""
        role = self._admin_role(self.db)
        stmt = (
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .options(selectinload(User.roles))
            .where(UserRole.role_id == role.id)
        )
        return list(self.db.execute(stmt).scalars())

    def active_admin_count(self) -> int:
        """当前仍可登录的管理员账号数（用于「至少保留一个」的守卫）。"""
        role = self._admin_role(self.db)
        return (
            self.db.execute(
                select(func.count(func.distinct(User.id)))
                .select_from(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role_id == role.id, User.status == UserStatus.ACTIVE)
            ).scalar()
            or 0
        )

    def _guard_last_active_admin(self, user: User, action: str) -> None:
        """若该操作会让系统一个可用管理员都不剩，则拒绝。

        只在该用户**当前确实是可登录的管理员**时才需要判断。
        """
        if user.status != UserStatus.ACTIVE or not self.is_admin(user):
            return
        if self.active_admin_count() <= 1:
            raise Conflict(f"系统至少需要保留一个可用的管理员账号，不能{action}唯一的管理员")

    def grant_admin(self, user_id: int, operator: User | None = None) -> User:
        """给既有账号授予管理员角色（用于教师兼任管理员）。

        **不改写 user_type**：教师仍是 TEACHER，教学班/课表/成绩等归属完全不变。
        """
        user = self.get_or_404(user_id)
        if self.is_admin(user):
            raise Conflict(f"{user.real_name}（{user.username}）已经是管理员")
        role = self._admin_role(self.db)
        self.db.add(UserRole(user_id=user.id, role_id=role.id))
        self._log(operator, "ADMIN_GRANT", user,
                  f"授予 {user.real_name}（{user.username}）管理员权限")
        self._commit()
        return self.get_or_404(user_id)

    def revoke_admin(self, user_id: int, operator: User | None = None) -> User:
        """撤销管理员角色。**不删除账号、不动任何教学数据**。"""
        user = self.get_or_404(user_id)
        if not self.is_admin(user):
            raise Conflict(f"{user.real_name}（{user.username}）不是管理员")
        if operator is not None and operator.id == user.id:
            raise Conflict("不能撤销当前登录账号自己的管理员权限，请由其他管理员操作")
        self._guard_last_active_admin(user, "撤销")
        role = self._admin_role(self.db)
        self.db.execute(
            delete(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id
            )
        )
        self._log(operator, "ADMIN_REVOKE", user,
                  f"撤销 {user.real_name}（{user.username}）管理员权限")
        self._commit()
        return self.get_or_404(user_id)

    def _log(self, operator: User | None, action: str, target: User, detail: str) -> None:
        """最小化审计：把管理员权限变更写入 operation_logs（含操作人与时间）。

        权限被撤销后仍可追溯：username 为冗余快照，user_id 置空不影响记录。
        """
        self.db.add(
            OperationLog(
                user_id=operator.id if operator else None,
                username=operator.username if operator else None,
                action=action,
                module="user",
                resource_type="user",
                resource_id=target.id,
                detail=detail[:500],
                result="SUCCESS",
            )
        )
