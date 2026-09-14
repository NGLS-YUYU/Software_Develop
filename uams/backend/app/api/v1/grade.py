"""成绩路由。"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student, Teacher
from app.models.user import User, UserType
from app.services.grade import GradeService

router = APIRouter(prefix="/grades", tags=["成绩"])


class GradeItem(BaseModel):
    grade_id: int
    regular_score: Decimal | None = Field(None, ge=0, le=100)
    final_score: Decimal | None = Field(None, ge=0, le=100)


class GradeBatchSave(BaseModel):
    teaching_class_id: int
    items: list[GradeItem]


class GradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_id: int
    student_no: str | None = None
    student_name: str | None = None
    teaching_class_id: int
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    semester: str
    regular_score: Decimal | None = None
    final_score: Decimal | None = None
    total_score: Decimal | None = None
    grade_point: Decimal | None = None
    credits: Decimal
    is_passed: bool | None = None
    status: str
    reject_reason: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None


class ApproveRequest(BaseModel):
    grade_ids: list[int] = Field(..., min_length=1)


class RejectRequest(BaseModel):
    grade_ids: list[int] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=500)


def _out(g) -> GradeOut:
    d = GradeOut.model_validate(g)
    if g.student:
        d.student_no = g.student.student_no
        d.student_name = g.student.user.real_name if g.student.user else None
    if g.course:
        d.course_code, d.course_name = g.course.code, g.course.name
    return d


def _me_teacher(db: Session, current: User) -> Teacher:
    if current.user_type != UserType.TEACHER:
        raise PermissionDenied("当前账号不是教师")
    t = db.execute(select(Teacher).where(Teacher.user_id == current.id)).scalar_one_or_none()
    if t is None:
        raise PermissionDenied("教师档案不存在")
    return t


def _me_student(db: Session, current: User) -> Student:
    if current.user_type != UserType.STUDENT:
        raise PermissionDenied("当前账号不是学生")
    s = db.execute(select(Student).where(Student.user_id == current.id)).scalar_one_or_none()
    if s is None:
        raise PermissionDenied("学生档案不存在")
    return s


# --- 学生 ---
@router.get("/mine", response_model=list[GradeOut], summary="我的成绩（仅已发布）")
def my_grades(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stu = _me_student(db, current)
    return [_out(g) for g in GradeService(db).list_by_student(stu.id, semester)]


@router.get("/mine/summary", summary="我的学分与绩点统计")
def my_summary(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    stu = _me_student(db, current)
    return GradeService(db).student_summary(stu.id)


# --- 教师 ---
@router.get(
    "/teaching-classes/{class_id}",
    response_model=list[GradeOut],
    summary="教学班成绩单",
)
def class_grades(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:read")),
):
    svc = GradeService(db)
    if current.user_type == UserType.TEACHER:
        svc.ensure_teacher_owns(_me_teacher(db, current), class_id)
    elif current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看整班成绩")
    return [_out(g) for g in svc.list_by_class(class_id)]


@router.post(
    "/teaching-classes/{class_id}/init",
    response_model=list[GradeOut],
    summary="生成成绩单（按已选学生，幂等）",
)
def init_sheet(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:write")),
):
    svc = GradeService(db)
    if current.user_type == UserType.TEACHER:
        svc.ensure_teacher_owns(_me_teacher(db, current), class_id)
    return [_out(g) for g in svc.init_sheet(class_id)]


@router.put("", response_model=list[GradeOut], summary="批量录入成绩（保存草稿）")
def save_grades(
    payload: GradeBatchSave,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:write")),
):
    teacher = _me_teacher(db, current)
    rows = GradeService(db).save_scores(
        teacher,
        payload.teaching_class_id,
        [i.model_dump(exclude_unset=True) for i in payload.items],
    )
    return [_out(g) for g in rows]


@router.post("/teaching-classes/{class_id}/submit", summary="提交成绩")
def submit_grades(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:submit")),
):
    teacher = _me_teacher(db, current)
    n = GradeService(db).submit(teacher, class_id)
    return {"submitted": n, "message": f"已提交 {n} 条成绩，等待教务审核"}


# --- 教务 ---
@router.get("/pending", response_model=list[GradeOut], summary="待审核成绩")
def pending(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("grade:approve")),
):
    return [_out(g) for g in GradeService(db).pending_approval(semester)]


@router.post("/approve", summary="审核通过")
def approve(
    payload: ApproveRequest,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:approve")),
):
    n = GradeService(db).approve(current.id, payload.grade_ids)
    return {"approved": n, "message": f"已通过 {n} 条成绩"}


@router.post("/reject", summary="驳回")
def reject(
    payload: RejectRequest,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:approve")),
):
    n = GradeService(db).reject(current.id, payload.grade_ids, payload.reason)
    return {"rejected": n, "message": f"已驳回 {n} 条成绩"}


@router.get(
    "/teaching-classes/{class_id}/statistics", summary="成绩分布统计"
)
def statistics(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:read")),
):
    svc = GradeService(db)
    if current.user_type == UserType.TEACHER:
        svc.ensure_teacher_owns(_me_teacher(db, current), class_id)
    elif current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看成绩统计")
    return svc.class_statistics(class_id)
