"""开课与排课路由。"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.db.session import get_db
from app.schemas.common import PageParams, PageResult
from app.schemas.teaching import (
    ScheduleCreate,
    ScheduleOut,
    TeachingClassCreate,
    TeachingClassOut,
    TeachingClassUpdate,
    TeachingTaskCreate,
    TeachingTaskOut,
    TeachingTaskUpdate,
)
from app.services.teaching import TeachingClassService, TeachingTaskService

router = APIRouter(tags=["开课排课"])
_read = Depends(get_current_user)


def _sched_out(s) -> ScheduleOut:
    d = ScheduleOut.model_validate(s)
    if s.classroom:
        d.classroom_code, d.building = s.classroom.code, s.classroom.building
    return d


def _task_out(t, svc) -> TeachingTaskOut:
    d = TeachingTaskOut.model_validate(t)
    if t.course:
        d.course_code, d.course_name = t.course.code, t.course.name
    d.college_name = t.college.name if t.college else None
    d.class_count = svc.class_count(t.id)
    return d


def _tc_out(tc) -> TeachingClassOut:
    d = TeachingClassOut.model_validate(tc)
    if tc.course:
        d.course_code, d.course_name = tc.course.code, tc.course.name
        d.credits = float(tc.course.credits)
    if tc.teacher and tc.teacher.user:
        d.teacher_name = tc.teacher.user.real_name
    d.remaining = max(0, tc.capacity - tc.selected_count)
    d.schedules = [_sched_out(s) for s in tc.schedules]
    return d


# =========================== 教学任务 ===========================
tasks = APIRouter(prefix="/teaching-tasks", tags=["开课排课-教学任务"])


@tasks.get("", response_model=PageResult[TeachingTaskOut], summary="教学任务列表")
def list_tasks(
    params: PageParams = Depends(),
    semester: str | None = Query(None),
    course_id: int | None = Query(None),
    college_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:read")),
):
    svc = TeachingTaskService(db)
    items, total = svc.paginate(
        params, semester=semester, course_id=course_id, college_id=college_id
    )
    return PageResult.build([_task_out(t, svc) for t in items], total, params)


@tasks.post(
    "",
    response_model=TeachingTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增教学任务",
)
def create_task(
    payload: TeachingTaskCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    svc = TeachingTaskService(db)
    t = svc.create(payload.model_dump())
    return _task_out(svc.get_or_404(t.id), svc)


@tasks.put("/{task_id}", response_model=TeachingTaskOut, summary="修改教学任务")
def update_task(
    task_id: int,
    payload: TeachingTaskUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    svc = TeachingTaskService(db)
    svc.update(task_id, payload.model_dump(exclude_unset=True))
    return _task_out(svc.get_or_404(task_id), svc)


@tasks.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教学任务")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    TeachingTaskService(db).delete(task_id)


# =========================== 教学班 ===========================
classes = APIRouter(prefix="/teaching-classes", tags=["开课排课-教学班"])


@classes.get("", response_model=PageResult[TeachingClassOut], summary="教学班列表")
def list_classes(
    params: PageParams = Depends(),
    semester: str | None = Query(None),
    course_id: int | None = Query(None),
    teacher_id: int | None = Query(None),
    selection_status: str | None = Query(None),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = TeachingClassService(db).paginate(
        params,
        semester=semester,
        course_id=course_id,
        teacher_id=teacher_id,
        selection_status=selection_status,
    )
    return PageResult.build([_tc_out(i) for i in items], total, params)


@classes.get("/{class_id}", response_model=TeachingClassOut, summary="教学班详情")
def get_class(class_id: int, db: Session = Depends(get_db), _=_read):
    return _tc_out(TeachingClassService(db).get_or_404(class_id))


@classes.post(
    "",
    response_model=TeachingClassOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增教学班",
)
def create_class(
    payload: TeachingClassCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    tc = TeachingClassService(db).create_class(payload.model_dump())
    return _tc_out(TeachingClassService(db).get_or_404(tc.id))


@classes.put("/{class_id}", response_model=TeachingClassOut, summary="修改教学班")
def update_class(
    class_id: int,
    payload: TeachingClassUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    svc = TeachingClassService(db)
    svc.update_class(class_id, payload.model_dump(exclude_unset=True))
    return _tc_out(svc.get_or_404(class_id))


@classes.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教学班")
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teaching:write")),
):
    TeachingClassService(db).delete(class_id)


@classes.post(
    "/{class_id}/selection",
    response_model=TeachingClassOut,
    summary="开放/关闭选课",
)
def toggle_selection(
    class_id: int,
    open: bool = Query(..., description="true 开放，false 关闭"),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("selection:manage")),
):
    svc = TeachingClassService(db)
    svc.open_selection(class_id, open)
    return _tc_out(svc.get_or_404(class_id))


# --- 排课 ---
@classes.get(
    "/{class_id}/schedules", response_model=list[ScheduleOut], summary="教学班排课"
)
def list_schedules(class_id: int, db: Session = Depends(get_db), _=_read):
    tc = TeachingClassService(db).get_or_404(class_id)
    return [_sched_out(s) for s in tc.schedules]


@classes.post(
    "/{class_id}/schedules",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
    summary="添加排课（自动检测教室/教师冲突）",
)
def add_schedule(
    class_id: int,
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    s = TeachingClassService(db).add_schedule(class_id, payload.model_dump())
    db.refresh(s)
    return _sched_out(s)


@classes.delete(
    "/{class_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除排课",
)
def remove_schedule(
    class_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    TeachingClassService(db).remove_schedule(class_id, schedule_id)


router.include_router(tasks)
router.include_router(classes)
