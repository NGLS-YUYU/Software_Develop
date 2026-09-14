"""SQLAlchemy 声明式基类与公共 Mixin。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的基类。

    统一使用 InnoDB + utf8mb4（DATABASE.md §1）。
    """

    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }


# 主键统一 BIGINT UNSIGNED AUTO_INCREMENT（DATABASE.md §1.1）
BigIntPK = BIGINT(unsigned=True)


class IdMixin:
    id: Mapped[int] = mapped_column(
        BigIntPK, primary_key=True, autoincrement=True, comment="主键"
    )


class TimestampMixin:
    """created_at / updated_at（DATABASE.md §1.2）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


def fk(target: str):
    """外键列类型辅助：保证与主键同为 BIGINT UNSIGNED。"""
    return BIGINT(unsigned=True)


__all__ = ["Base", "BigIntPK", "IdMixin", "TimestampMixin", "fk", "BigInteger"]
