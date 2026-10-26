"""教学资料上传/下载（F-21）。"""
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, is_admin_user
from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.db.session import get_db
from app.models.material import TeachingMaterial
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.models.user import User, UserType

router = APIRouter(prefix="/materials", tags=["教学资料"])
BACKEND = Path(__file__).resolve().parents[2]
MATERIAL_DIR = BACKEND / "uploads" / "materials"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".zip", ".png", ".jpg", ".jpeg"}


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    teaching_class_id: int
    teaching_class_code: str | None = None
    title: str
    file_name: str
    file_size: int
    content_type: str | None = None
    uploader_name: str | None = None
    created_at: datetime | None = None


def _out(m: TeachingMaterial) -> MaterialOut:
    d = MaterialOut.model_validate(m)
    if m.teaching_class:
        d.teaching_class_code = m.teaching_class.code
    d.uploader_name = m.uploader.real_name if m.uploader else None
    return d


def _teacher(db: Session, user: User) -> Teacher | None:
    return db.execute(select(Teacher).where(Teacher.user_id == user.id)).scalar_one_or_none()


def _student(db: Session, user: User) -> Student | None:
    return db.execute(select(Student).where(Student.user_id == user.id)).scalar_one_or_none()


def _can_view(db: Session, user: User, tc: TeachingClass) -> bool:
    if is_admin_user(user):
        return True
    if user.user_type == UserType.TEACHER:
        me = _teacher(db, user)
        return me is not None and tc.teacher_id == me.id
    if user.user_type == UserType.STUDENT:
        stu = _student(db, user)
        if stu is None:
            return False
        return db.execute(
            select(CourseSelection.id).where(
                CourseSelection.student_id == stu.id,
                CourseSelection.teaching_class_id == tc.id,
                CourseSelection.status == SelectionState.SELECTED,
            ).limit(1)
        ).scalar_one_or_none() is not None
    return False


@router.get("", response_model=list[MaterialOut], summary="教学资料列表")
def list_materials(
    teaching_class_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TeachingClass, teaching_class_id)
    if tc is None:
        raise NotFound("教学班不存在")
    if not _can_view(db, current, tc):
        raise PermissionDenied("无权查看该教学班资料")
    rows = db.execute(
        select(TeachingMaterial)
        .options(selectinload(TeachingMaterial.uploader), selectinload(TeachingMaterial.teaching_class))
        .where(TeachingMaterial.teaching_class_id == tc.id)
        .order_by(TeachingMaterial.created_at.desc())
    ).scalars()
    return [_out(m) for m in rows]


@router.get("/my", response_model=list[MaterialOut], summary="我可查看的教学资料")
def my_materials(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if is_admin_user(current):
        tc_ids = select(TeachingClass.id)
    elif current.user_type == UserType.TEACHER:
        me = _teacher(db, current)
        if me is None:
            return []
        tc_ids = select(TeachingClass.id).where(TeachingClass.teacher_id == me.id)
    elif current.user_type == UserType.STUDENT:
        stu = _student(db, current)
        if stu is None:
            return []
        tc_ids = select(CourseSelection.teaching_class_id).where(
            CourseSelection.student_id == stu.id,
            CourseSelection.status == SelectionState.SELECTED,
        )
    else:
        return []
    rows = db.execute(
        select(TeachingMaterial)
        .options(selectinload(TeachingMaterial.uploader), selectinload(TeachingMaterial.teaching_class))
        .where(TeachingMaterial.teaching_class_id.in_(tc_ids))
        .order_by(TeachingMaterial.created_at.desc())
    ).scalars()
    return [_out(m) for m in rows]


@router.post("", response_model=MaterialOut, status_code=status.HTTP_201_CREATED, summary="上传教学资料")
async def upload_material(
    teaching_class_id: int = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.user_type not in (UserType.TEACHER, UserType.ADMIN) and not is_admin_user(current):
        raise PermissionDenied("只有教师或管理员可以上传教学资料")
    tc = db.get(TeachingClass, teaching_class_id)
    if tc is None:
        raise NotFound("教学班不存在")
    if not _can_view(db, current, tc):
        raise PermissionDenied("只能上传本人授课教学班的资料")
    name = Path(file.filename or "material").name
    if len(name) > 255:
        raise Conflict("文件名不能超过 255 个字符")
    title = title.strip()
    if not title:
        raise Conflict("资料标题不能为空")
    if len(title) > 200:
        raise Conflict("资料标题不能超过 200 个字符")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise Conflict("不支持的文件类型（仅 pdf/doc/ppt/xls/txt/zip/图片）")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise Conflict("文件不能超过 10MB")
    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    stored = MATERIAL_DIR / f"{uuid4().hex}{suffix}"
    stored.write_bytes(content)
    m = TeachingMaterial(
        teaching_class_id=tc.id,
        title=title,
        file_name=name,
        file_path=str(stored),
        file_size=len(content),
        content_type=(file.content_type or "")[:100] or None,
        uploaded_by=current.id,
    )
    try:
        db.add(m)
        db.commit()
        db.refresh(m)
    except Exception:
        db.rollback()
        stored.unlink(missing_ok=True)
        raise
    return _out(m)


@router.get("/{material_id}/download", summary="下载教学资料")
def download_material(
    material_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    m = db.get(TeachingMaterial, material_id)
    if m is None or m.teaching_class is None:
        raise NotFound("教学资料不存在")
    if not _can_view(db, current, m.teaching_class):
        raise PermissionDenied("无权下载该资料")
    path = Path(m.file_path)
    if not path.is_file():
        raise NotFound("资料文件不存在")
    return FileResponse(path, filename=m.file_name, media_type=m.content_type or "application/octet-stream")


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教学资料")
def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    m = db.get(TeachingMaterial, material_id)
    if m is None or m.teaching_class is None:
        raise NotFound("教学资料不存在")
    if not _can_view(db, current, m.teaching_class):
        raise PermissionDenied("无权删除该资料")
    if current.user_type == UserType.STUDENT:
        raise PermissionDenied("学生不能删除教学资料")
    path = Path(m.file_path)
    db.delete(m)
    db.commit()
    path.unlink(missing_ok=True)
