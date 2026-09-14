"""认证路由（CLAUDE.md §11：Router 只负责 HTTP 请求与响应）。"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    UserInfo,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse, summary="登录")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    user = service.authenticate(payload.username, payload.password)
    token, expires_in = service.issue_token(user)

    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserInfo.model_validate(user),
        roles=service.role_codes(user),
        permissions=service.permission_codes(user),
        home_route=service.home_route(user),
    )


@router.get("/me", response_model=CurrentUserResponse, summary="当前用户信息")
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        user=UserInfo.model_validate(user),
        roles=AuthService.role_codes(user),
        permissions=AuthService.permission_codes(user),
    )


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="修改密码",
)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    AuthService(db).change_password(user, payload.old_password, payload.new_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="退出登录")
def logout(user: User = Depends(get_current_user)) -> None:
    """JWT 无状态，服务端不维护会话，由前端丢弃 token。

    预留此接口是为了记录退出操作日志，并保持前端调用形式统一。
    """
    return None
