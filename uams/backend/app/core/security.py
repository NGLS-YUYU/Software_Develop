"""密码哈希与 JWT。

不使用 passlib：它依赖 bcrypt.__about__，该属性在 bcrypt 4.1+ 已移除，
在 bcrypt 5.x 下会直接报错。这里直接调用 bcrypt，行为更可控。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt 只取密码前 72 字节，超长部分被静默丢弃。
# 显式截断并在校验时用同样规则，避免"超长密码任意后缀都能登录"。
_BCRYPT_MAX_BYTES = 72


def _truncate(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # 哈希串格式非法（如脏数据）时按验证失败处理，不抛异常
        return False


def create_access_token(
    subject: str | int,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解码并校验 token；无效或过期返回 None。"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload
