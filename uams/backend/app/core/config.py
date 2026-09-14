"""应用配置。

所有敏感配置通过环境变量或 .env 注入，不写入源码（CLAUDE.md §23）。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- 应用 ---
    APP_NAME: str = "UAMS"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- 数据库 ---
    DATABASE_URL: str = Field(
        default="mysql+pymysql://uams_app:888888@127.0.0.1:3306/uams?charset=utf8mb4"
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600  # MySQL 默认 wait_timeout 8 小时，提前回收避免断连

    # --- 认证 ---
    JWT_SECRET: str = Field(default="CHANGE_ME_IN_ENV")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # --- 登录失败限制（CLAUDE.md §23）---
    MAX_LOGIN_FAILURES: int = 5
    LOGIN_LOCK_MINUTES: int = 15

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
