"""选课路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user, is_admin_user
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student
from app.models.selection import SelectionPeriod
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.schemas.teaching import TeachingClassOut
from app.services.person import StudentService
from app.services.selection import SelectionService, selection_source_label
from app.services.teaching import TeachingClassService

router = APIRouter(tags=["选课"])


class SelectionCreate(BaseModel):
    teaching_class_id: int


class ClassStudentAdd(BaseModel):
    student_id: int


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_id: int
    teaching_class_id: int
    teaching_class_code: str | None = None
    term_id: int | None = None
    term_name: str | None = None
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    course_type: str | None = None
    credits: float | None = None
    teacher_name: str | None = None
    semester: str
    status: str
    teaching_class_status: str | None = None
    selection_status: str | None = None
    source: str | None = None
    source_label: str | None = None
    selected_at: datetime | None = None


class RequiredAssign(BaseModel):
    college_id: int | None = None
    major_id: int | None = None
    class_id: int | None = None


class StudentBrief(BaseModel):
    selection_id: int
    student_id: int
    student_no: str
    real_name: str
    major: str | None = None
    class_name: str | None = None
    status: str
    source: str | None = None
    source_label: str | None = None
    selected_at: datetime | None = None


class RequiredAssignItem(BaseModel):
    student_id: int
    student_no: str
    student_name: str
    class_name: str | None = None
    major_name: str | None = None
    action: str = Field(..., pattern="^(ADD|ALREADY|SKIP)$")
    reason_code: str | None = None
    reason: str | None = None


class RequiredAssignResult(BaseModel):
    teaching_class_id: int
    teaching_class_code: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    scope: dict[str, int]
    matched: int
    already_assigned: int
    would_add: int
    added: int
    skipped: int
    capacity: int
    selected_count: int
    selected_count_after: int
    remaining: int
    remaining_after: int
    conflict_count: int
    ineligible_count: int
    reason_counts: dict[str, int] = {}
    preview: bool
    committed: bool
    items: list[RequiredAssignItem] = []


class SelectionPeriodCreate(BaseModel):
    semester: str = Field(..., pattern=r"^\d{4}-\d{4}-[1-3]$")
    name: str = Field(..., max_length=50)
    start_time: datetime
    end_time: datetime
    target_grade_year: int | None = Field(None, ge=1900, le=2200)
    status: str = Field("PENDING", pattern="^(PENDING|ACTIVE|CLOSED)$")

    @model_validator(mode="after")
    def check_window_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class SelectionPeriodOut(SelectionPeriodCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    time_state: str = "INACTIVE"
    term_status: str | None = None
    is_effective: bool = False


class SelectionWindowOut(BaseModel):
    id: int
    name: str
    start_time: datetime
    end_time: datetime
    target_grade_year: int | None = None
    status: str


class SelectionWindowStatus(BaseModel):
    semester: str
    term_status: str | None = None
    can_select: bool
    can_drop: bool
    reason_code: str | None = None
    reason: str | None = None
    window: SelectionWindowOut | None = None
    open_windows: list[SelectionWindowOut] = []


def _period_out(p, db: Session, now: datetime | None = None) -> SelectionPeriodOut:
    d = SelectionPeriodOut.model_validate(p)
    now = now or datetime.now()
    if p.status != "ACTIVE":
        state = "INACTIVE"
    elif now < p.start_time:
        state = "NOT_STARTED"
    elif now > p.end_time:
        state = "EXPIRED"
    else:
        state = "OPEN"
    # 时间开放不等于实际生效：学期必须存在且 ACTIVE。
    parts = (p.semester or "").rsplit("-", 1)
    term = None
    if len(parts) == 2 and parts[1] in ("1", "2"):
        term = db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == parts[0],
                AcademicTerm.semester == int(parts[1]),
            )
        ).scalar_one_or_none()
    d.time_state = state
    d.term_status = term.status if term else None
    d.is_effective = (
        state == "OPEN"
        and term is not None
        and term.status == "ACTIVE"
    )
    return d


def _window_out(data: dict | None) -> SelectionWindowOut | None:
    if not data:
        return None
    return SelectionWindowOut.model_validate(data)


def _sel_out(s) -> SelectionOut:
    d = SelectionOut.model_validate(s)
    d.source = s.source
    d.source_label = selection_source_label(s.source)
    if s.course:
        d.course_code, d.course_name = s.course.code, s.course.name
        d.credits = float(s.course.credits)
        d.course_type = s.course.course_type
    if s.teaching_class:
        d.teaching_class_code = s.teaching_class.code
        d.teaching_class_status = s.teaching_class.status
        d.selection_status = s.teaching_class.selection_status
        t = s.teaching_class.teacher
        if t and t.user:
            d.teacher_name = t.user.real_name
        if s.teaching_class.term:
            d.term_id = s.teaching_class.term.id
            d.term_name = s.teaching_class.term.name
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
    svc = SelectionService(db)
    # F-06：窗口未开放/年级不符/学期非 ACTIVE 时不再展示“看得见却选不了”的课程。
    if not svc.selection_window_status(stu, semester)["can_select"]:
        return []
    rows = svc.available_classes(stu, semester, keyword)
    counts = TeachingClassService(db).selection_counts([r.id for r in rows])
    return [_tc_out(r, counts.get(r.id, 0)) for r in rows]


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


@sel.get(
    "/window",
    response_model=SelectionWindowStatus,
    summary="当前选课窗口状态（学生）",
)
def window_status(
    semester: str = Query(..., description="学期，如 2026-2027-1"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """统一返回学期/窗口/年级判断结果，供学生端显示与按钮状态使用。"""
    stu = _current_student(db, current)
    state = SelectionService(db).selection_window_status(stu, semester)
    return SelectionWindowStatus(
        semester=state["semester"],
        term_status=state["term_status"],
        can_select=state["can_select"],
        can_drop=state["can_drop"],
        reason_code=state["reason_code"],
        reason=state["reason"],
        window=_window_out(state["window"]),
        open_windows=[SelectionWindowOut.model_validate(w) for w in state["open_windows"]],
    )


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
    if current.user_type == UserType.TEACHER and not is_admin_user(current):
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
                selection_id=s.id,
                student_id=stu.id,
                student_no=stu.student_no,
                real_name=stu.user.real_name if stu.user else "",
                major=stu.major.name if stu.major else None,
                class_name=stu.klass.name if stu.klass else None,
                status=s.status,
                source=s.source,
                source_label=selection_source_label(s.source),
                selected_at=s.selected_at,
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


@mgmt.post(
    "/{class_id}/students",
    status_code=status.HTTP_201_CREATED,
    summary="教务添加学生到教学班",
)
def add_student_to_class(
    class_id: int,
    payload: ClassStudentAdd,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:manage")),
):
    """教务处手动将学生加入教学班（FIX-002）。

    与批量预排共用容量、学期、学籍、同课程、时间冲突校验；来源记为 ADMIN_MANUAL。
    """
    sel = TeachingClassService(db).add_student(
        class_id, payload.student_id, operator=current
    )
    return {
        "selection_id": sel.id,
        "student_id": payload.student_id,
        "teaching_class_id": class_id,
        "source": sel.source,
        "source_label": selection_source_label(sel.source),
        "message": "已加入教学班",
    }


@mgmt.delete(
    "/{class_id}/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="教务移除教学班学生",
)
def remove_student_from_class(
    class_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:manage")),
):
    """教务处将学生从教学班移除（FIX-002）；已有成绩记录时拒绝。"""
    TeachingClassService(db).remove_student(
        class_id, student_id, operator=current
    )


@mgmt.post(
    "/{class_id}/assign-required",
    response_model=RequiredAssignResult,
    summary="必修课预安排（按学院/专业/行政班，支持预览）",
)
def assign_required(
    class_id: int,
    payload: RequiredAssign,
    preview: bool = Query(
        False, description="true=只预览不写库；false=正式提交"
    ),
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("selection:manage")),
):
    """教务处将必修课程按范围（class_id > major_id > college_id）安排给学生。

    - ``preview=true``：返回匹配/新增/跳过/容量/冲突明细，不写库；
    - ``preview=false``：在单事务内写入可新增记录，逐条返回跳过原因；
    - 已在本班的学生返回 ALREADY；曾被移除的学生返回 PREVIOUSLY_REMOVED。
    """
    return SelectionService(db).assign_required(
        class_id,
        college_id=payload.college_id,
        major_id=payload.major_id,
        class_id=payload.class_id,
        preview=preview,
        operator=current,
    )


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
    return [_period_out(p, db) for p in db.execute(stmt).scalars()]


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
    return _period_out(p, db)


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
    return _period_out(p, db)


router.include_router(sel)
router.include_router(mgmt)
router.include_router(periods)
