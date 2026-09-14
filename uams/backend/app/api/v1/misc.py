"""教学评价、通知公告、数据统计、审计日志路由。"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.db.session import get_db
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.misc import Announcement, Evaluation, EvaluationTask, OperationLog
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.models.user import User, UserType
from app.schemas.common import PageParams, PageResult

router = APIRouter()


def _me_student(db: Session, current: User) -> Student:
    if current.user_type != UserType.STUDENT:
        raise PermissionDenied("当前账号不是学生")
    s = db.execute(select(Student).where(Student.user_id == current.id)).scalar_one_or_none()
    if s is None:
        raise PermissionDenied("学生档案不存在")
    return s


# =========================== 教学评价 ===========================
evals = APIRouter(prefix="/evaluations", tags=["教学评价"])


class EvalTaskCreate(BaseModel):
    name: str = Field(..., max_length=100)
    semester: str = Field(..., pattern=r"^\d{4}-\d{4}-[1-3]$")
    start_time: datetime
    end_time: datetime
    status: str = Field("PENDING", pattern="^(PENDING|ACTIVE|CLOSED)$")


class EvalTaskOut(EvalTaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class EvalSubmit(BaseModel):
    task_id: int
    teaching_class_id: int
    score: Decimal = Field(..., ge=0, le=100)
    comment: str | None = Field(None, max_length=1000)


class EvalStats(BaseModel):
    teaching_class_id: int
    teaching_class_code: str | None = None
    course_name: str | None = None
    teacher_name: str | None = None
    count: int
    average: float | None = None
    comments: list[str] = []


@evals.get("/tasks", response_model=list[EvalTaskOut], summary="评价任务列表")
def list_tasks(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(EvaluationTask)
    if semester:
        stmt = stmt.where(EvaluationTask.semester == semester)
    return [EvalTaskOut.model_validate(t) for t in db.execute(stmt).scalars()]


@evals.post(
    "/tasks",
    response_model=EvalTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建评价任务",
)
def create_task(
    payload: EvalTaskCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("evaluation:manage")),
):
    t = EvaluationTask(**payload.model_dump())
    db.add(t)
    db.commit()
    return EvalTaskOut.model_validate(t)


@evals.get("/pending", summary="我待评价的课程")
def my_pending(
    task_id: int = Query(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stu = _me_student(db, current)
    task = db.get(EvaluationTask, task_id)
    if task is None:
        raise NotFound("评价任务不存在")

    done = {
        e.teaching_class_id
        for e in db.execute(
            select(Evaluation).where(
                Evaluation.task_id == task_id, Evaluation.student_id == stu.id
            )
        ).scalars()
    }
    rows = db.execute(
        select(TeachingClass)
        .options(
            selectinload(TeachingClass.course),
            selectinload(TeachingClass.teacher).selectinload(Teacher.user),
        )
        .join(CourseSelection, CourseSelection.teaching_class_id == TeachingClass.id)
        .where(
            CourseSelection.student_id == stu.id,
            CourseSelection.status == SelectionState.SELECTED,
            TeachingClass.semester == task.semester,
        )
    ).scalars()
    return [
        {
            "teaching_class_id": tc.id,
            "teaching_class_code": tc.code,
            "course_name": tc.course.name if tc.course else None,
            "teacher_name": tc.teacher.user.real_name
            if tc.teacher and tc.teacher.user
            else None,
            "evaluated": tc.id in done,
        }
        for tc in rows
    ]


@evals.post("", status_code=status.HTTP_201_CREATED, summary="提交评价")
def submit_eval(
    payload: EvalSubmit,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("evaluation:write")),
):
    stu = _me_student(db, current)
    task = db.get(EvaluationTask, payload.task_id)
    if task is None:
        raise NotFound("评价任务不存在")
    if not task.is_open_now():
        raise Conflict("当前不在评价开放期内")

    tc = db.get(TeachingClass, payload.teaching_class_id)
    if tc is None:
        raise NotFound("教学班不存在")
    if tc.teacher_id is None:
        raise Conflict("该教学班未分配教师，无法评价")

    sel = db.execute(
        select(CourseSelection).where(
            CourseSelection.student_id == stu.id,
            CourseSelection.teaching_class_id == tc.id,
            CourseSelection.status == SelectionState.SELECTED,
        )
    ).scalar_one_or_none()
    if sel is None:
        raise PermissionDenied("只能评价本人所选的课程")

    if db.execute(
        select(Evaluation).where(
            Evaluation.task_id == task.id,
            Evaluation.student_id == stu.id,
            Evaluation.teaching_class_id == tc.id,
        )
    ).scalar_one_or_none():
        raise Conflict("已评价过该课程，不能重复提交")

    db.add(
        Evaluation(
            task_id=task.id,
            student_id=stu.id,
            teaching_class_id=tc.id,
            teacher_id=tc.teacher_id,
            score=payload.score,
            comment=payload.comment,
        )
    )
    db.commit()
    return {"message": "评价已提交"}


@evals.get(
    "/statistics", response_model=list[EvalStats], summary="评价统计（匿名聚合）"
)
def eval_statistics(
    task_id: int | None = Query(None),
    teaching_class_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("evaluation:read")),
):
    """只返回聚合结果，绝不下发 student_id（PRD §8.8 匿名性）。"""
    stmt = select(Evaluation)
    if task_id:
        stmt = stmt.where(Evaluation.task_id == task_id)
    if teaching_class_id:
        stmt = stmt.where(Evaluation.teaching_class_id == teaching_class_id)

    # 教师只能看自己的评价
    if current.user_type == UserType.TEACHER:
        me = db.execute(
            select(Teacher).where(Teacher.user_id == current.id)
        ).scalar_one_or_none()
        if me is None:
            raise PermissionDenied("教师档案不存在")
        stmt = stmt.where(Evaluation.teacher_id == me.id)
    elif current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看评价统计")

    grouped: dict[int, list[Evaluation]] = {}
    for e in db.execute(stmt).scalars():
        grouped.setdefault(e.teaching_class_id, []).append(e)

    out = []
    for tcid, items in grouped.items():
        tc = db.get(TeachingClass, tcid)
        scores = [float(i.score) for i in items]
        out.append(
            EvalStats(
                teaching_class_id=tcid,
                teaching_class_code=tc.code if tc else None,
                course_name=tc.course.name if tc and tc.course else None,
                teacher_name=tc.teacher.user.real_name
                if tc and tc.teacher and tc.teacher.user
                else None,
                count=len(scores),
                average=round(sum(scores) / len(scores), 2) if scores else None,
                # 只给评语文本，不带任何学生标识
                comments=[i.comment for i in items if i.comment],
            )
        )
    return out


# =========================== 通知公告 ===========================
anns = APIRouter(prefix="/announcements", tags=["通知公告"])


class AnnCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str = Field(..., min_length=1)
    target_type: str = Field("ALL", pattern="^(ALL|STUDENT|TEACHER)$")
    is_top: bool = False


class AnnUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: str | None = None
    target_type: str | None = Field(None, pattern="^(ALL|STUDENT|TEACHER)$")
    is_top: bool | None = None
    status: str | None = Field(None, pattern="^(DRAFT|PUBLISHED|WITHDRAWN)$")


class AnnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    target_type: str
    is_top: bool
    status: str
    publisher_id: int
    publisher_name: str | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None


def _ann_out(a) -> AnnOut:
    d = AnnOut.model_validate(a)
    d.publisher_name = a.publisher.real_name if a.publisher else None
    return d


@anns.get("", response_model=PageResult[AnnOut], summary="公告列表")
def list_anns(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stmt = select(Announcement).options(selectinload(Announcement.publisher))
    # 非教务只能看到已发布、且面向自己角色的公告
    if current.user_type != UserType.ADMIN:
        target = "STUDENT" if current.user_type == UserType.STUDENT else "TEACHER"
        stmt = stmt.where(
            Announcement.status == "PUBLISHED",
            Announcement.target_type.in_(["ALL", target]),
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(
        stmt.order_by(Announcement.is_top.desc(), Announcement.published_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).scalars()
    return PageResult.build([_ann_out(a) for a in rows], total, params)


@anns.post(
    "", response_model=AnnOut, status_code=status.HTTP_201_CREATED, summary="发布公告"
)
def create_ann(
    payload: AnnCreate,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("announcement:write")),
):
    a = Announcement(**payload.model_dump(), publisher_id=current.id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _ann_out(a)


@anns.put("/{ann_id}", response_model=AnnOut, summary="修改/发布/撤回公告")
def update_ann(
    ann_id: int,
    payload: AnnUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("announcement:write")),
):
    a = db.get(Announcement, ann_id)
    if a is None:
        raise NotFound("公告不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") == "PUBLISHED" and a.published_at is None:
        a.published_at = datetime.now()
    for k, v in data.items():
        if v is not None:
            setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return _ann_out(a)


@anns.delete("/{ann_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除公告")
def delete_ann(
    ann_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("announcement:write")),
):
    a = db.get(Announcement, ann_id)
    if a is None:
        raise NotFound("公告不存在")
    db.delete(a)
    db.commit()


# =========================== 数据统计 ===========================
stats = APIRouter(prefix="/statistics", tags=["数据统计"])


@stats.get("/overview", summary="教务工作台概览")
def overview(
    db: Session = Depends(get_db), _=Depends(RequirePermissions("statistics:read"))
):
    def cnt(model, *w):
        return db.execute(select(func.count()).select_from(model).where(*w)).scalar() or 0

    return {
        "colleges": cnt(College),
        "majors": cnt(Major),
        "classes": cnt(Class),
        "students": cnt(Student),
        "teachers": cnt(Teacher),
        "courses": cnt(Course),
        "teaching_classes": cnt(TeachingClass),
        "selections": cnt(CourseSelection, CourseSelection.status == SelectionState.SELECTED),
        "pending_grades": cnt(Grade, Grade.status == GradeStatus.SUBMITTED),
    }


@stats.get("/grade-distribution", summary="全校成绩分布")
def grade_distribution(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("statistics:read")),
):
    stmt = select(Grade).where(
        Grade.status == GradeStatus.APPROVED, Grade.total_score.is_not(None)
    )
    if semester:
        stmt = stmt.where(Grade.semester == semester)
    scores = [float(g.total_score) for g in db.execute(stmt).scalars()]
    if not scores:
        return {"count": 0}
    b = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
    for s in scores:
        if s >= 90: b["90-100"] += 1
        elif s >= 80: b["80-89"] += 1
        elif s >= 70: b["70-79"] += 1
        elif s >= 60: b["60-69"] += 1
        else: b["<60"] += 1
    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 2),
        "pass_rate": round(len([s for s in scores if s >= 60]) / len(scores) * 100, 2),
        "distribution": b,
    }


@stats.get("/selection-ranking", summary="课程选课热度排行")
def selection_ranking(
    semester: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("statistics:read")),
):
    rows = db.execute(
        select(Course.name, func.count(CourseSelection.id).label("n"))
        .join(CourseSelection, CourseSelection.course_id == Course.id)
        .where(
            CourseSelection.semester == semester,
            CourseSelection.status == SelectionState.SELECTED,
        )
        .group_by(Course.id, Course.name)
        .order_by(func.count(CourseSelection.id).desc())
        .limit(limit)
    ).all()
    return [{"course_name": n, "selected": c} for n, c in rows]


# =========================== 审计日志 ===========================
audit = APIRouter(prefix="/audit-logs", tags=["审计日志"])


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    module: str
    resource_type: str | None = None
    resource_id: int | None = None
    detail: str | None = None
    ip_address: str | None = None
    result: str
    created_at: datetime


@audit.get("", response_model=PageResult[LogOut], summary="操作日志")
def list_logs(
    params: PageParams = Depends(),
    action: str | None = Query(None),
    user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("audit:read")),
):
    stmt = select(OperationLog)
    if action:
        stmt = stmt.where(OperationLog.action == action)
    if user_id:
        stmt = stmt.where(OperationLog.user_id == user_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(
        stmt.order_by(OperationLog.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    ).scalars()
    return PageResult.build([LogOut.model_validate(r) for r in rows], total, params)


for r in (evals, anns, stats, audit):
    router.include_router(r)
