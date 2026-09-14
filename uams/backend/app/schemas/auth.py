"""认证相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="学号/工号/用户名")
    password: str = Field(..., min_length=1, max_length=128)


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    user_type: str
    email: str | None = None
    phone: str | None = None
    status: str
    last_login_at: datetime | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserInfo
    roles: list[str]
    permissions: list[str]
    home_route: str = Field(..., description="按角色跳转的默认首页（PRD §11.2）")


class CurrentUserResponse(BaseModel):
    user: UserInfo
    roles: list[str]
    permissions: list[str]


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)
