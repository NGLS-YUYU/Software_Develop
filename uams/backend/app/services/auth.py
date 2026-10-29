"""认证业务逻辑（CLAUDE.md §11：业务逻辑集中在 Service 层）。"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AccountDisabled,
    AccountLocked,
    InvalidCredentials,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models.role import RoleCode
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository

# 登录后按角色跳转（PRD §11.2）
HOME_ROUTES = {
    RoleCode.STUDENT: "/student/dashboard",
    RoleCode.TEACHER: "/teacher/dashboard",
    RoleCode.ACADEMIC_ADMIN: "/admin/dashboard",
}
DEFAULT_HOME = "/dashboard"


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    # --- 查询辅助 ---

    @staticmethod
    def role_codes(user: User) -> list[str]:
        return sorted(r.code for r in user.roles)

    @staticmethod
    def permission_codes(user: User) -> list[str]:
        codes = {p.code for r in user.roles for p in r.permissions}
        return sorted(codes)

    @classmethod
    def home_route(cls, user: User) -> str:
        for code in cls.role_codes(user):
            if code in HOME_ROUTES:
                return HOME_ROUTES[code]
        return DEFAULT_HOME

    # --- 登录 ---

    def authenticate(self, username: str, real_name: str, password: str) -> User:
        user = self.repo.get_by_username(username)

        # 用户不存在时也走一次哈希校验，避免通过响应时间区分
        # "用户不存在" 与 "密码错误"（用户名枚举）
        if user is None:
            verify_password(password, "$2b$12$" + "x" * 53)
            raise InvalidCredentials()

        now = datetime.now()

        if user.locked_until and user.locked_until > now:
            raise self._locked_error(user.locked_until, now)

        if user.status == UserStatus.DISABLED:
            raise AccountDisabled()

        # 姓名与密码同时校验，任一失败统一计入失败次数。
        password_ok = verify_password(password, user.password_hash)
        name_ok = self._name_matches(user, real_name.strip())
        if not (password_ok and name_ok):
            locked_until = self._record_failure(user, now)
            if locked_until is not None:
                # 触发锁定当次即返回锁定状态，避免用户继续尝试却只看到“凭据错误”。
                raise self._locked_error(locked_until, now)
            raise InvalidCredentials()

        # 登录成功：清零失败计数
        user.failed_login_count = 0
        user.locked_until = None
        user.status = UserStatus.ACTIVE if user.status == UserStatus.LOCKED else user.status
        user.last_login_at = now
        self.db.commit()
        return user

    @staticmethod
    def _name_matches(user: User, real_name: str) -> bool:
        """姓名精确匹配（去首尾空白）；初始 admin 兼容姓名 admin。

        User.real_name 是统一权威姓名来源；Student/Teacher 不另存姓名。
        初始 admin 在历史库中可能显示为“系统管理员”，因此仅对 username=admin
        额外接受 admin，不修改任何历史身份资料。
        """
        expected = (user.real_name or "").strip()
        if real_name and real_name == expected:
            return True
        return user.username == "admin" and real_name == "admin"

    @staticmethod
    def _locked_error(locked_until: datetime, now: datetime) -> AccountLocked:
        """锁定错误附带到期时间与剩余秒数，供前端显示真实剩余时间。"""
        remaining = max(1, int((locked_until - now).total_seconds()))
        return AccountLocked(
            f"账号已锁定，请于 {locked_until:%Y-%m-%d %H:%M} 后重试",
            locked_until=locked_until.isoformat(sep=" ", timespec="seconds"),
            retry_after_seconds=remaining,
        )

    def _record_failure(self, user: User, now: datetime) -> datetime | None:
        """登录失败限制（CLAUDE.md §23）。返回本次触发的锁定到期时间。"""
        user.failed_login_count += 1
        locked_until = None
        if user.failed_login_count >= settings.MAX_LOGIN_FAILURES:
            locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            user.locked_until = locked_until
            user.status = UserStatus.LOCKED
            user.failed_login_count = 0
        self.db.commit()
        return locked_until

    def issue_token(self, user: User) -> tuple[str, int]:
        token = create_access_token(
            subject=user.id,
            extra={"username": user.username, "user_type": user.user_type},
        )
        return token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # --- 改密 ---

    def change_password(self, user: User, old: str, new: str) -> None:
        if not verify_password(old, user.password_hash):
            raise InvalidCredentials("原密码错误")
        user.password_hash = hash_password(new)
        self.db.commit()
