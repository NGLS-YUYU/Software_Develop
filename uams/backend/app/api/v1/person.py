"""学生、教师路由。

数据权限（CLAUDE.md §9）：
  - 学生只能访问自己的档案
  - 教师可查看学生（用于名单），但不能修改
  - 教务可管理全部
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student, Teacher
from app.models.user import User, UserType
from app.schemas.common import PageParams, PageResult
from app.schemas.person import (
    StudentCreate,
    StudentOut,
    StudentUpdate,
    TeacherCreate,
    TeacherOut,
    TeacherUpdate,
)
from app.services.person import StudentService, TeacherService

router = APIRouter(tags=["人员管理"])


def _student_out(s: Student) -> StudentOut:
    d = StudentOut.model_validate(s)
    d.real_name = s.user.real_name if s.user else ""
    d.email = s.user.email if s.user else None
    d.phone = s.user.phone if s.user else None
    d.class_name = s.klass.name if s.klass else None
    d.major_name = s.major.name if s.major else None
    d.college_name = s.college.name if s.college else None
    return d


def _teacher_out(t: Teacher) -> TeacherOut:
    d = TeacherOut.model_validate(t)
    d.real_name = t.user.real_name if t.user else ""
    d.email = t.user.email if t.user else None
    d.phone = t.user.phone if t.user else None
    d.college_name = t.college.name if t.college else None
    return d


def _assert_can_view_student(current: User, stu: Student) -> None:
    """对象级权限校验（PRD §4.3：不能只依赖角色级菜单控制）。"""
    if current.user_type == UserType.STUDENT and stu.user_id != current.id:
        raise PermissionDenied("只能查看本人信息")


# =========================== 学生 ===========================
students = APIRouter(prefix="/students", tags=["人员管理-学生"])


@students.get("", response_model=PageResult[StudentOut], summary="学生列表")
def list_students(
    params: PageParams = Depends(),
    class_id: int | None = Query(None),
    major_id: int | None = Query(None),
    college_id: int | None = Query(None),
    academic_status: str | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("student:read")),
):
    # 学生无 student:read 权限，走不到这里；此处再挡一次纵深防御
    if current.user_type == UserType.STUDENT:
        raise PermissionDenied("无权查看学生列表")
    items, total = StudentService(db).paginate(
        params,
        class_id=class_id,
        major_id=major_id,
        college_id=college_id,
        academic_status=academic_status,
    )
    return PageResult.build([_student_out(i) for i in items], total, params)


@students.get("/me", response_model=StudentOut, summary="我的学生档案")
def my_student_profile(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    from sqlalchemy import select

    stu = db.execute(
        StudentService(db).base_stmt().where(Student.user_id == current.id)
    ).scalar_one_or_none()
    if stu is None:
        raise PermissionDenied("当前账号不是学生")
    _ = select  # 保持 import 使用
    return _student_out(stu)


@students.get("/{student_id}", response_model=StudentOut, summary="学生详情")
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stu = StudentService(db).get_or_404(student_id)
    _assert_can_view_student(current, stu)
    return _student_out(stu)


@students.post(
    "", response_model=StudentOut, status_code=status.HTTP_201_CREATED, summary="新增学生"
)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("student:write")),
):
    return _student_out(StudentService(db).create_student(payload.model_dump()))


@students.put("/{student_id}", response_model=StudentOut, summary="修改学生")
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("student:write")),
):
    return _student_out(
        StudentService(db).update_student(
            student_id, payload.model_dump(exclude_unset=True)
        )
    )


@students.delete(
    "/{student_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除学生"
)
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("student:write")),
):
    StudentService(db).delete(student_id)


# =========================== 教师 ===========================
teachers = APIRouter(prefix="/teachers", tags=["人员管理-教师"])


@teachers.get("", response_model=PageResult[TeacherOut], summary="教师列表")
def list_teachers(
    params: PageParams = Depends(),
    college_id: int | None = Query(None),
    title: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teacher:read")),
):
    items, total = TeacherService(db).paginate(params, college_id=college_id, title=title)
    return PageResult.build([_teacher_out(i) for i in items], total, params)


@teachers.get("/me", response_model=TeacherOut, summary="我的教师档案")
def my_teacher_profile(
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    t = db.execute(
        TeacherService(db).base_stmt().where(Teacher.user_id == current.id)
    ).scalar_one_or_none()
    if t is None:
        raise PermissionDenied("当前账号不是教师")
    return _teacher_out(t)


@teachers.get("/{teacher_id}", response_model=TeacherOut, summary="教师详情")
def get_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teacher:read")),
):
    return _teacher_out(TeacherService(db).get_or_404(teacher_id))


@teachers.post(
    "", response_model=TeacherOut, status_code=status.HTTP_201_CREATED, summary="新增教师"
)
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teacher:write")),
):
    return _teacher_out(TeacherService(db).create_teacher(payload.model_dump()))


@teachers.put("/{teacher_id}", response_model=TeacherOut, summary="修改教师")
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teacher:write")),
):
    return _teacher_out(
        TeacherService(db).update_teacher(
            teacher_id, payload.model_dump(exclude_unset=True)
        )
    )


@teachers.delete(
    "/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教师"
)
def delete_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("teacher:write")),
):
    TeacherService(db).delete(teacher_id)


router.include_router(students)
router.include_router(teachers)
