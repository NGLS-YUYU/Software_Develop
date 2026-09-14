"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    course,
    exam,
    grade,
    misc,
    organization,
    person,
    schedule,
    selection,
    teaching,
)

api_router = APIRouter()
for _m in (
    auth,
    organization,
    person,
    course,
    teaching,
    selection,
    schedule,
    grade,
    exam,
    misc,
):
    api_router.include_router(_m.router)

__all__ = ["api_router"]
