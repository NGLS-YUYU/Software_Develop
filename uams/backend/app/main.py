"""UAMS 应用入口。"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.db.session import engine

app = FastAPI(
    title="UAMS 高校教务教学管理系统",
    description="University Academic Affairs & Teaching Management System",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一错误响应格式（PRD §13.2：错误必须有可识别的错误码和说明）。"""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        body = detail
    else:
        body = {"code": f"HTTP_{exc.status_code}", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "errors": [
                {"field": ".".join(str(x) for x in e["loc"][1:]), "msg": e["msg"]}
                for e in exc.errors()
            ],
        },
    )


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["系统"])
def health() -> dict:
    """健康检查：确认应用与数据库连通。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "database": "up" if db_ok else "down",
    }
