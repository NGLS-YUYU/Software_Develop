"""统一业务异常与错误码。

PRD §13.2 要求 API 错误返回可识别的错误码和说明。
"""

from fastapi import HTTPException, status


class BizError(HTTPException):
    """业务异常基类。

    响应体形如 {"code": "AUTH_INVALID_CREDENTIALS", "message": "..."}。
    """

    code = "BIZ_ERROR"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "业务处理失败"

    def __init__(self, message: str | None = None, **extra):
        self.extra = extra
        super().__init__(
            status_code=self.http_status,
            detail={"code": self.code, "message": message or self.message, **extra},
        )


# --- 认证 ---
class InvalidCredentials(BizError):
    code = "AUTH_INVALID_CREDENTIALS"
    http_status = status.HTTP_401_UNAUTHORIZED
    message = "用户名或密码错误"


class AccountLocked(BizError):
    code = "AUTH_ACCOUNT_LOCKED"
    http_status = status.HTTP_423_LOCKED
    message = "账号已被锁定，请稍后再试"


class AccountDisabled(BizError):
    code = "AUTH_ACCOUNT_DISABLED"
    http_status = status.HTTP_403_FORBIDDEN
    message = "账号已被停用"


class InvalidToken(BizError):
    code = "AUTH_INVALID_TOKEN"
    http_status = status.HTTP_401_UNAUTHORIZED
    message = "登录状态无效或已过期"


# --- 权限 ---
class PermissionDenied(BizError):
    code = "PERM_DENIED"
    http_status = status.HTTP_403_FORBIDDEN
    message = "无权执行该操作"


# --- 资源 ---
class NotFound(BizError):
    code = "RESOURCE_NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND
    message = "资源不存在"


class Conflict(BizError):
    code = "RESOURCE_CONFLICT"
    http_status = status.HTTP_409_CONFLICT
    message = "资源冲突"
