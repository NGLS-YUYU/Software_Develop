"""教学安排（排课）管理路由（TASK-013）。

复用既有 ``Schedule`` 模型（`schedules` 表）作为教学安排实体，不新建表；
权限复用既有 ``schedule:read`` / ``schedule:write``（不新增 ``teaching_schedule:*``）。

角色隔离（CLAUDE.md §9）：
  - 教务（ACADEMIC_ADMIN）：完整增删改查；
  - 教师：仅 /mine 查询本人授课教学班的安排；
  - 学生：仅 /my 查询本人已选教学班的安排。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, RequireRoles, get_current_user
from app.api.v1.teaching import _sched_out
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student, Teacher
from app.models.user import User, UserType
from app.schemas.common import BatchDeleteRequest, BatchDeleteResult
from app.schemas.teaching import ScheduleOut, ScheduleUpdate, TeachingScheduleCreate
from app.services.base import batch_delete_each
from app.services.teaching import ScheduleService

router = APIRouter(prefix="/teaching-schedules", tags=["教学安排"])


def _teacher_of(db: Session, current: User) -> Teacher:
    t = db.execute(
        select(Teacher).where(Teacher.user_id == current.id)
    ).scalar_one_or_none()
    if t is None:
        raise PermissionDenied("教师档案不存在")
    return t


def _student_of(db: Session, current: User) -> Student:
    s = db.execute(
        select(Student).where(Student.user_id == current.id)
    ).scalar_one_or_none()
    if s is None:
        raise PermissionDenied("学生档案不存在")
    return s


# --- 教务：完整管理 ---


@router.get("", response_model=list[ScheduleOut], summary="教学安排列表（教务）")
def list_schedules(
    term_id: int | None = Query(None, description="学期过滤"),
    teaching_class_id: int | None = Query(None, description="教学班过滤"),
    teacher_id: int | None = Query(None, description="教师过滤"),
    weekday: int | None = Query(None, ge=1, le=7, description="星期过滤 1-7"),
    classroom: str | None = Query(None, description="教室编号过滤"),
    db: Session = Depends(get_db),
    _=Depends(RequireRoles("ACADEMIC_ADMIN")),
):
    rows = ScheduleService(db).list(
        term_id=term_id,
        teaching_class_id=teaching_class_id,
        teacher_id=teacher_id,
        weekday=weekday,
        classroom=classroom,
    )
    return [_sched_out(r) for r in rows]


@router.post(
    "",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增教学安排（自动检测教学班/教室/教师冲突）",
)
def create_schedule(
    payload: TeachingScheduleCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    s = ScheduleService(db).create(payload.model_dump())
    return _sched_out(ScheduleService(db).get_or_404(s.id))


# --- 教师：本人授课教学班的安排 ---


@router.get(
    "/mine", response_model=list[ScheduleOut], summary="我的教学安排（教师）"
)
def my_teaching_schedules(
    term_id: int | None = Query(None, description="学期过滤（academic_terms.id）"),
    semester: str | None = Query(None, description="字符串学期过滤，如 2026-2027-1"),
    week: int | None = Query(None, ge=1, le=30, description="第几周，不填返回全部"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """教师本人授课教学班的排课；身份取自 token，不接受 teacher_id（FIX-007 起为课表数据源）。"""
    if current.user_type != UserType.TEACHER:
        raise PermissionDenied("仅教师可查询本人教学安排")
    t = _teacher_of(db, current)
    return [
        _sched_out(r)
        for r in ScheduleService(db).mine_for_teacher(
            t.id, term_id, semester=semester, week=week
        )
    ]


# --- 学生：本人已选教学班的安排 ---


@router.get(
    "/my", response_model=list[ScheduleOut], summary="我的课程安排（学生）"
)
def my_course_schedules(
    term_id: int | None = Query(None, description="学期过滤（academic_terms.id）"),
    semester: str | None = Query(None, description="字符串学期过滤，如 2026-2027-1"),
    week: int | None = Query(None, ge=1, le=30, description="第几周，不填返回全部"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """学生本人已选教学班的排课；未选课返回空列表（FIX-007 起为课表数据源）。"""
    if current.user_type != UserType.STUDENT:
        raise PermissionDenied("仅学生可查询本人课程安排")
    s = _student_of(db, current)
    return [
        _sched_out(r)
        for r in ScheduleService(db).mine_for_student(
            s.id, term_id, semester=semester, week=week
        )
    ]


@router.get("/{schedule_id}", response_model=ScheduleOut, summary="教学安排详情（教务）")
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequireRoles("ACADEMIC_ADMIN")),
):
    return _sched_out(ScheduleService(db).get_or_404(schedule_id))


@router.put("/{schedule_id}", response_model=ScheduleOut, summary="修改教学安排")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    s = ScheduleService(db).update(schedule_id, payload.model_dump(exclude_unset=True))
    return _sched_out(ScheduleService(db).get_or_404(s.id))


@router.post(
    "/batch-delete", response_model=BatchDeleteResult, summary="批量删除教学安排"
)
def batch_delete_schedules(
    payload: BatchDeleteRequest,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    svc = ScheduleService(db)
    return batch_delete_each(payload.ids, svc.delete)


@router.delete(
    "/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教学安排"
)
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    ScheduleService(db).delete(schedule_id)
