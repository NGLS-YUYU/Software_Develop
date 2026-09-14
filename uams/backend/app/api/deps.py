"""FastAPI 依赖：当前用户、角色校验、权限校验。

CLAUDE.md §9：任何 API 都必须进行后端权限验证，
不能仅依靠前端隐藏菜单实现权限控制。
"""

from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AccountDisabled, InvalidToken, PermissionDenied
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise InvalidToken("缺少认证信息")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise InvalidToken()

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise InvalidToken()

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise InvalidToken("用户不存在")

    # 签发 token 后账号可能被停用/锁定，每次请求都要复查
    if user.status != UserStatus.ACTIVE:
        raise AccountDisabled("账号状态异常，请重新登录")

    return user


class RequireRoles:
    """角色校验依赖。

        @router.get(..., dependencies=[Depends(RequireRoles("ACADEMIC_ADMIN"))])
    """

    def __init__(self, *role_codes: str):
        self.role_codes = set(role_codes)

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if not self.role_codes & set(AuthService.role_codes(user)):
            raise PermissionDenied(
                f"需要以下角色之一: {', '.join(sorted(self.role_codes))}"
            )
        return user


class RequirePermissions:
    """权限校验依赖。

    默认要求全部权限（AND）；传 require_all=False 表示任一即可（OR）。
    """

    def __init__(self, *permission_codes: str, require_all: bool = True):
        self.permission_codes = set(permission_codes)
        self.require_all = require_all

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        owned = set(AuthService.permission_codes(user))
        ok = (
            self.permission_codes <= owned
            if self.require_all
            else bool(self.permission_codes & owned)
        )
        if not ok:
            missing = self.permission_codes - owned
            raise PermissionDenied(f"缺少权限: {', '.join(sorted(missing))}")
        return user
