"""用户账号管理路由（TASK-001：用户管理权限）。

仅教务管理员（user:read / user:write）可访问。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PageParams, PageResult
from app.schemas.user import (
    ResetPasswordRequest,
    UserCreate,
    UserOut,
    UserStatusUpdate,
)
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["用户管理"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        real_name=u.real_name,
        user_type=u.user_type,
        email=u.email,
        phone=u.phone,
        status=u.status,
        last_login_at=u.last_login_at,
        roles=[r.code for r in u.roles],
    )


@router.get("", response_model=PageResult[UserOut], summary="用户列表")
def list_users(
    params: PageParams = Depends(),
    user_type: str | None = Query(None, description="STUDENT/TEACHER/ADMIN"),
    status: str | None = Query(None, description="ACTIVE/DISABLED/LOCKED"),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("user:read")),
):
    items, total = UserService(db).paginate(
        params, user_type=user_type, status=status
    )
    return PageResult.build([_user_out(i) for i in items], total, params)


@router.get("/{user_id}", response_model=UserOut, summary="用户详情")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("user:read")),
):
    return _user_out(UserService(db).get_or_404(user_id))


@router.post(
    "", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="新建账号"
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("user:write")),
):
    return _user_out(UserService(db).create_user(payload.model_dump()))


@router.put(
    "/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT, summary="重置密码"
)
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("user:write")),
):
    UserService(db).reset_password(user_id, payload.new_password)


@router.put("/{user_id}/status", response_model=UserOut, summary="停用/启用账号")
def set_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("user:write")),
):
    return _user_out(UserService(db).set_status(user_id, payload.status))
