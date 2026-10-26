"""用户账号管理 Schema（TASK-001：用户管理）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.email import EmailField


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="登录名")
    real_name: str = Field(..., min_length=1, max_length=50)
    user_type: str = Field(..., pattern="^(STUDENT|TEACHER|ADMIN)$")
    password: str = Field(..., min_length=6, max_length=128)
    role_codes: list[str] = Field(
        default_factory=list, description="角色代码；为空则按 user_type 分配默认角色"
    )
    email: EmailField = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)


class UserStatusUpdate(BaseModel):
    # 只允许手动停用/启用；LOCKED 由登录失败机制自动管理，不可手动设置
    status: str = Field(..., pattern="^(ACTIVE|DISABLED)$")


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    user_type: str
    email: str | None = None
    phone: str | None = None
    status: str
    last_login_at: datetime | None = None
    roles: list[str] = Field(default_factory=list, description="角色代码")
