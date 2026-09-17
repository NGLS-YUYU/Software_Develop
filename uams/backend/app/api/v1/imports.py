"""Excel 批量导入路由（TASK-010）。

仅教务（ADMIN / ACADEMIC_ADMIN）可调用；TEACHER / STUDENT 返回 403。
权限复用现有 student:write / course:write / grade:write。
"""

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import Conflict
from app.db.session import get_db
from app.models.user import User
from app.services.import_service import ImportService

router = APIRouter(prefix="/imports", tags=["批量导入"])

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_response(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=_XLSX_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _validate_ext(filename: str | None) -> None:
    if not filename or not filename.lower().endswith(".xlsx"):
        raise Conflict("仅支持 .xlsx 格式文件")


# =========================== 模板下载 ===========================


@router.get("/templates/students", summary="学生导入模板下载")
def student_template(
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("student:write")),
):
    return _xlsx_response(
        ImportService(db).student_template(), "student_import_template.xlsx"
    )


@router.get("/templates/courses", summary="课程导入模板下载")
def course_template(
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("course:write")),
):
    return _xlsx_response(
        ImportService(db).course_template(), "course_import_template.xlsx"
    )


@router.get("/templates/grades", summary="成绩导入模板下载")
def grade_template(
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("grade:write")),
):
    return _xlsx_response(
        ImportService(db).grade_template(), "grade_import_template.xlsx"
    )


# =========================== 批量导入 ===========================


@router.post("/students", summary="批量导入学生")
async def import_students(
    file: UploadFile,
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("student:write")),
):
    _validate_ext(file.filename)
    content = await file.read()
    return ImportService(db).import_students(content)


@router.post("/courses", summary="批量导入课程")
async def import_courses(
    file: UploadFile,
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("course:write")),
):
    _validate_ext(file.filename)
    content = await file.read()
    return ImportService(db).import_courses(content)


@router.post("/grades", summary="批量导入成绩")
async def import_grades(
    file: UploadFile,
    db: Session = Depends(get_db),
    _: User = Depends(RequirePermissions("grade:write")),
):
    _validate_ext(file.filename)
    content = await file.read()
    return ImportService(db).import_grades(content)
