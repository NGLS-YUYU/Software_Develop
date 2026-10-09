"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    course,
    exam,
    grade,
    imports,
    misc,
    organization,
    person,
    schedule,
    selection,
    teaching,
    teaching_schedule,
    terms,
    user,
)

api_router = APIRouter()
for _m in (
    auth,
    user,
    organization,
    person,
    course,
    teaching,
    selection,
    schedule,
    teaching_schedule,
    terms,
    grade,
    exam,
    imports,
    misc,
):
    api_router.include_router(_m.router)

# 管理员管理使用独立前缀 /admins（与账号管理 /users 分开）
api_router.include_router(user.admins)

__all__ = ["api_router"]
