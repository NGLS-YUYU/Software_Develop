"""邮箱相关 Service 公共逻辑（FIX-001）。

Schema 层已经用 ``EmailField`` 做了一次规范化；这里再提供：
  - ``normalize_email_or_error``：把 ValueError 转成统一的 400 业务异常；
  - ``ensure_email_available``：在写库前做可读的唯一性预检查。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import normalize_email
from app.core.exceptions import EmailAlreadyExists, InvalidEmail
from app.models.user import User


def normalize_email_or_error(value: str | None) -> str | None:
    """规范化邮箱；格式错误转成 ``InvalidEmail``（HTTP 400）。"""
    try:
        return normalize_email(value)
    except ValueError as exc:
        raise InvalidEmail(str(exc)) from exc


def ensure_email_available(
    db: Session,
    email: str | None,
    exclude_user_id: int | None = None,
) -> None:
    """非空邮箱必须未被其他用户占用。

    MySQL 的 ``users.email`` 唯一索引使用 utf8mb4_0900_ai_ci，
    比较本身大小写不敏感；这里保持与数据库一致的语义。
    """
    if email is None:
        return
    stmt = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    if db.execute(stmt.limit(1)).first() is not None:
        raise EmailAlreadyExists()
