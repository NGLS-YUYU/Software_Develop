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
from app.services.assessment import profile_for
from app.services.grade import GradeService

router = APIRouter(prefix="/grades", tags=["成绩"])


class GradeItem(BaseModel):
    grade_id: int
    regular_score: Decimal | None = Field(None, ge=0, le=100)
    mid_score: Decimal | None = Field(None, ge=0, le=100)
    mid_theory_score: Decimal | None = Field(None, ge=0, le=100)
    mid_practice_score: Decimal | None = Field(None, ge=0, le=100)
    final_score: Decimal | None = Field(None, ge=0, le=100)
    final_theory_score: Decimal | None = Field(None, ge=0, le=100)
    final_practice_score: Decimal | None = Field(None, ge=0, le=100)
    theory_makeup_score: Decimal | None = Field(None, ge=0, le=100)
    practice_makeup_score: Decimal | None = Field(None, ge=0, le=100)


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
    teaching_class_code: str | None = None
    teacher_name: str | None = None
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    assessment_type: str | None = None
    has_midterm: bool | None = None
    has_practice: bool | None = None
    course_total_hours: int | None = None
    course_theory_hours: int | None = None
    semester: str
    regular_score: Decimal | None = None
    mid_score: Decimal | None = None
    mid_theory_score: Decimal | None = None
    mid_practice_score: Decimal | None = None
    final_score: Decimal | None = None
    final_theory_score: Decimal | None = None
    final_practice_score: Decimal | None = None
    theory_makeup_score: Decimal | None = None
    practice_makeup_score: Decimal | None = None
    theory_total_score: Decimal | None = None
    practice_total_score: Decimal | None = None
    total_score: Decimal | None = None
    grade_point: Decimal | None = None
    credits: Decimal
    is_passed: bool | None = None
    status: str
    reject_reason: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    course_practice_hours: int | None = None


class ApproveRequest(BaseModel):
    grade_ids: list[int] = Field(..., min_length=1)


class RejectRequest(BaseModel):
    grade_ids: list[int] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=500)


class RosterStudent(BaseModel):
    student_id: int
    student_no: str
    student_name: str
    grade_id: int | None = None
    entry_status: str  # NOT_ENTERED / DRAFT / SUBMITTED / APPROVED / REJECTED


class StudentGradeOverview(BaseModel):
    """学生成绩查询结果（TASK-007）：成绩明细 + 实时 GPA + 班级/专业排名。"""

    items: list[GradeOut]
    gpa: float | None = None
    class_rank: int | None = None
    major_rank: int | None = None


def _out(g) -> GradeOut:
    d = GradeOut.model_validate(g)
    if g.student:
        d.student_no = g.student.student_no
        d.student_name = g.student.user.real_name if g.student.user else None
    if g.course:
        d.course_code, d.course_name = g.course.code, g.course.name
        # 考核结构由课程总学时/实践学时统一推导，不信任存量 assessment_type（FIX-009）
        profile = profile_for(g.course)
        d.assessment_type = profile.assessment_type
        d.has_midterm = profile.has_midterm
        d.has_practice = profile.has_practice
        d.course_total_hours = g.course.total_hours
        d.course_theory_hours = g.course.theory_hours
        d.course_practice_hours = g.course.practice_hours
    if g.teaching_class:
        d.teaching_class_code = g.teaching_class.code
        t = g.teaching_class.teacher
        if t and t.user:
            d.teacher_name = t.user.real_name
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


@router.get("/my", response_model=StudentGradeOverview, summary="我的成绩（含 GPA 与排名）")
def my_grades_overview(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """学生查看自己的已审核成绩，并附带实时 GPA 与班级/专业排名（TASK-007）。

    学生身份取自 token，不接受任何 student_id/user_id 参数，天然杜绝越权。
    """
    stu = _me_student(db, current)
    data = GradeService(db).student_overview(stu)
    return StudentGradeOverview(
        items=[_out(g) for g in data["grades"]],
        gpa=float(data["gpa"]) if data["gpa"] is not None else None,
        class_rank=data["class_rank"],
        major_rank=data["major_rank"],
    )


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


@router.get(
    "/teaching-classes/{class_id}/students",
    response_model=list[RosterStudent],
    summary="课程学生名单（含成绩录入状态）",
)
def class_roster(
    class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:read")),
):
    """教师查看本人授课教学班的学生名单及成绩状态（TASK-005）。"""
    svc = GradeService(db)
    if current.user_type == UserType.TEACHER:
        svc.ensure_teacher_owns(_me_teacher(db, current), class_id)
    elif current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看学生名单")
    return svc.roster(class_id)


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


@router.delete(
    "/{grade_id}",
    status_code=204,
    summary="删除成绩草稿（仅 DRAFT，SUBMITTED/APPROVED 返回 409）",
)
def delete_grade(
    grade_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("grade:write")),
):
    """删除成绩草稿（FIX-005 §十二~§十五）。

    教师只能删除本人授课教学班的草稿；教务可删除任意草稿。
    非草稿状态由 Service 统一拒绝（409）。
    """
    if current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权删除成绩")
    teacher = _me_teacher(db, current) if current.user_type == UserType.TEACHER else None
    GradeService(db).delete_draft(teacher, grade_id)


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
