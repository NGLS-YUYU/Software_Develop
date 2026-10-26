"""关键业务操作审计写入（F-09）。"""

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.misc import OperationLog


def write_log(
    db: Session,
    *,
    action: str,
    module: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    detail: str | None = None,
    result: str = "SUCCESS",
    user_id: int | None = None,
    username: str | None = None,
    request: Request | None = None,
    commit: bool = True,
) -> None:
    ip = None
    ua = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
    db.add(
        OperationLog(
            user_id=user_id,
            username=username,
            action=action[:50],
            module=module[:40],
            resource_type=(resource_type or "")[:40] or None,
            resource_id=resource_id,
            detail=(detail or "")[:500] or None,
            ip_address=ip,
            user_agent=(ua or "")[:300] or None,
            result=result,
        )
    )
    if commit:
        db.commit()
