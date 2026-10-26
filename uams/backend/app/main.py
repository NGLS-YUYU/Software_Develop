"""UAMS 应用入口。"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import SessionLocal, engine
from app.services.audit import write_log

app = FastAPI(
    title="UAMS 高校教务教学管理系统",
    description="University Academic Affairs & Teaching Management System",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
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


@app.middleware("http")
async def audit_mutation_middleware(request: Request, call_next):
    """记录已认证用户的写操作（POST/PUT/PATCH/DELETE），不读取请求体/密码（F-09）。"""
    path = request.url.path
    method = request.method.upper()
    should_log = (
        path.startswith(settings.API_V1_PREFIX + "/")
        and method in {"POST", "PUT", "PATCH", "DELETE"}
        and not path.startswith(settings.API_V1_PREFIX + "/auth/login")
    )
    response = await call_next(request)
    if should_log:
        try:
            token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
            payload = decode_access_token(token) if token else None
            user_id = int(payload["sub"]) if payload and payload.get("sub") else None
            username = payload.get("username") if payload else None
            parts = [p for p in path.split("/") if p]
            module = parts[2] if len(parts) > 2 else "api"
            resource_id = next((int(p) for p in parts[::-1] if p.isdigit()), None)
            resource_type = module
            with SessionLocal() as audb:
                write_log(
                    audb,
                    action=f"{method} {parts[-1] if parts else ''}",
                    module=module,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    detail=f"{method} {path} -> {response.status_code}",
                    result="SUCCESS" if response.status_code < 400 else "FAILURE",
                    user_id=user_id,
                    username=username,
                    request=request,
                )
        except Exception:
            # 审计失败不影响主业务
            pass
    return response


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
