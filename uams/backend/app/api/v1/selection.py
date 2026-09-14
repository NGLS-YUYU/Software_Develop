"""选课路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student
from app.models.selection import SelectionPeriod
from app.models.user import User, UserType
from app.schemas.teaching import TeachingClassOut
from app.services.person import StudentService
from app.services.selection import SelectionService
from app.services.teaching import TeachingClassService

router = APIRouter(tags=["选课"])


class SelectionCreate(BaseModel):
    teaching_class_id: int


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_id: int
    teaching_class_id: int
    teaching_class_code: str | None = None
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    credits: float | None = None
    teacher_name: str | None = None
    semester: str
    status: str
    selected_at: datetime | None = None


class StudentBrief(BaseModel):
    student_id: int
    student_no: str
    real_name: str
    class_name: str | None = None


class SelectionPeriodCreate(BaseModel):
    semester: str = Field(..., pattern=r"^\d{4}-\d{4}-[1-3]$")
    name: str = Field(..., max_length=50)
    start_time: datetime
    end_time: datetime
    target_grade_year: int | None = None
    status: str = Field("PENDING", pattern="^(PENDING|ACTIVE|CLOSED)$")


class SelectionPeriodOut(SelectionPeriodCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


def _sel_out(s) -> SelectionOut:
    d = SelectionOut.model_validate(s)
    if s.course:
        d.course_code, d.course_name = s.course.code, s.course.name
        d.credits = float(s.course.credits)
    if s.teaching_class:
        d.teaching_class_code = s.teaching_class.code
        t = s.teaching_class.teacher
        if t and t.user:
            d.teacher_name = t.user.real_name
    return d


def _current_student(db: Session, current: User) -> Student:
    if current.user_type != UserType.STUDENT:
        raise PermissionDenied("当前账号不是学生")
    stu = db.execute(
        select(Student).where(Student.user_id == current.id)
    ).scalar_one_or_none()
    if stu is None:
        raise PermissionDenied("学生档案不存在")
    return stu


# =========================== 学生选课 ===========================
sel = APIRouter(prefix="/course-selections", tags=["选课-学生"])


@sel.get("/available", response_model=list[TeachingClassOut], summary="可选课程")
def available(
    semester: str = Query(..., description="学期，如 2026-2027-1"),
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    from app.api.v1.teaching import _tc_out

    stu = _current_student(db, current)
    rows = SelectionService(db).available_classes(stu, semester, keyword)
    return [_tc_out(r) for r in rows]


@sel.get("/mine", response_model=list[SelectionOut], summary="我的选课")
def my_selections(
    semester: str | None = Query(None),
    include_dropped: bool = Query(False),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stu = _current_student(db, current)
    rows = SelectionService(db).list_by_student(stu.id, semester, include_dropped)
    return [_sel_out(r) for r in rows]


@sel.post(
    "", response_model=SelectionOut, status_code=status.HTTP_201_CREATED, summary="选课"
)
def create_selection(
    payload: SelectionCreate,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:write")),
):
    stu = _current_student(db, current)
    svc = SelectionService(db)
    s = svc.select_course(stu, payload.teaching_class_id)
    row = db.execute(svc.base_stmt().where(type(s).id == s.id)).scalar_one()
    return _sel_out(row)


@sel.delete("/{selection_id}", status_code=status.HTTP_204_NO_CONTENT, summary="退课")
def drop_selection(
    selection_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:write")),
):
    stu = _current_student(db, current)
    SelectionService(db).drop_course(stu, selection_id)


# =========================== 教务/教师视角 ===========================
mgmt = APIRouter(prefix="/teaching-classes", tags=["选课-管理"])


@mgmt.get(
    "/{class_id}/students", response_model=list[StudentBrief], summary="教学班学生名单"
)
def class_students(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:read")),
):
    """教师只能查看本人授课教学班的名单（CLAUDE.md §9）。"""
    tc = TeachingClassService(db).get_or_404(class_id)
    if current.user_type == UserType.TEACHER:
        from app.models.person import Teacher

        me = db.execute(
            select(Teacher).where(Teacher.user_id == current.id)
        ).scalar_one_or_none()
        if me is None or tc.teacher_id != me.id:
            raise PermissionDenied("只能查看本人授课教学班的学生名单")
    elif current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看学生名单")

    out = []
    for s in SelectionService(db).list_by_class(class_id):
        stu = s.student
        out.append(
            StudentBrief(
                student_id=stu.id,
                student_no=stu.student_no,
                real_name=stu.user.real_name if stu.user else "",
                class_name=stu.klass.name if stu.klass else None,
            )
        )
    return out


@mgmt.get("/{class_id}/selection-stats", summary="选课统计（含计数一致性检查）")
def selection_stats(
    class_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("selection:read")),
):
    return SelectionService(db).stats_by_class(class_id)


# =========================== 选课时间窗口 ===========================
periods = APIRouter(prefix="/selection-periods", tags=["选课-时间窗口"])


@periods.get("", response_model=list[SelectionPeriodOut], summary="选课时间窗口列表")
def list_periods(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(SelectionPeriod)
    if semester:
        stmt = stmt.where(SelectionPeriod.semester == semester)
    return [
        SelectionPeriodOut.model_validate(p) for p in db.execute(stmt).scalars()
    ]


@periods.post(
    "",
    response_model=SelectionPeriodOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增选课时间窗口",
)
def create_period(
    payload: SelectionPeriodCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("selection:manage")),
):
    p = SelectionPeriod(**payload.model_dump())
    db.add(p)
    db.commit()
    return SelectionPeriodOut.model_validate(p)


@periods.put("/{period_id}", response_model=SelectionPeriodOut, summary="修改时间窗口")
def update_period(
    period_id: int,
    payload: SelectionPeriodCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("selection:manage")),
):
    from app.core.exceptions import NotFound

    p = db.get(SelectionPeriod, period_id)
    if p is None:
        raise NotFound("选课时间窗口不存在")
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return SelectionPeriodOut.model_validate(p)


router.include_router(sel)
router.include_router(mgmt)
router.include_router(periods)
