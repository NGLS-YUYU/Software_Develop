"""SQLAlchemy IntegrityError → 业务异常映射（FIX-001）。

原则：
  - 只把可识别的唯一约束映射成明确的 409，不把所有重复都写成“邮箱重复”；
  - 未知 IntegrityError 继续抛出，避免吞掉真正的程序错误；
  - 在 flush 阶段失败时先 rollback，防止留下孤立账号/档案。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, EmailAlreadyExists


def conflict_from_integrity_error(
    exc: IntegrityError, entity_name: str
) -> Conflict | None:
    """根据数据库错误信息返回业务异常；无法识别时返回 None。"""
    msg = str(exc.orig) if exc.orig else str(exc)
    low = msg.lower()

    # 先匹配带表名的索引，避免把其他表的 email 误判。
    if "users.email" in low or "'email'" in low:
        return EmailAlreadyExists()
    if "users.username" in low or "'username'" in low:
        return Conflict("登录名已存在，请更换登录名")
    if "students.student_no" in low or "'student_no'" in low:
        return Conflict("学号已存在")
    if "teachers.teacher_no" in low or "'teacher_no'" in low:
        return Conflict("工号已存在")

    if "foreign key" in low:
        return Conflict(
            f"操作被拒绝：{entity_name}存在关联数据或引用的数据不存在"
        )
    if "duplicate" in low:
        return Conflict(f"{entity_name}存在重复数据，请检查唯一字段")
    return None


def flush_or_conflict(db: Session, entity_name: str) -> None:
    """执行 ``db.flush()``，失败时回滚并转换为业务异常。

    用于“先 flush、后继续建档案”的创建流程；如果 flush 失败，
    rollback 会撤销本事务中已写入的 users/档案/角色关联。
    """
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        conflict = conflict_from_integrity_error(exc, entity_name)
        if conflict is not None:
            raise conflict from exc
        raise
