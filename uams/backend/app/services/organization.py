"""组织结构业务逻辑。"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import Conflict, NotFound
from app.models.organization import Class, Classroom, College, Major
from app.models.person import Student, Teacher
from app.models.teaching import Schedule
from app.services.base import BaseCrudService


class CollegeService(BaseCrudService[College]):
    model = College
    search_fields = ("code", "name")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "学院"

    def validate_delete(self, obj: College) -> None:
        # 学院被专业/教师/课程引用时不允许删除（DATABASE.md §1.5 RESTRICT）
        for m, label in ((Major, "专业"), (Teacher, "教师")):
            n = self.db.execute(
                select(func.count()).select_from(m).where(m.college_id == obj.id)
            ).scalar()
            if n:
                raise Conflict(f"该学院下还有 {n} 个{label}，无法删除")


class MajorService(BaseCrudService[Major]):
    model = Major
    search_fields = ("code", "name")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "专业"

    def base_stmt(self) -> Select:
        return select(Major).options(selectinload(Major.college))

    def validate_create(self, data: dict[str, Any]) -> None:
        if not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")

    def validate_update(self, obj: Major, data: dict[str, Any]) -> None:
        if "college_id" in data and not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")

    def validate_delete(self, obj: Major) -> None:
        n = self.db.execute(
            select(func.count()).select_from(Class).where(Class.major_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该专业下还有 {n} 个班级，无法删除")


class ClassService(BaseCrudService[Class]):
    model = Class
    search_fields = ("code", "name")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "班级"

    def base_stmt(self) -> Select:
        return select(Class).options(selectinload(Class.major))

    def validate_create(self, data: dict[str, Any]) -> None:
        if not self.db.get(Major, data["major_id"]):
            raise NotFound(f"专业不存在（id={data['major_id']}）")
        cid = data.get("counselor_id")
        if cid and not self.db.get(Teacher, cid):
            raise NotFound(f"辅导员不存在（id={cid}）")

    def validate_update(self, obj: Class, data: dict[str, Any]) -> None:
        if "major_id" in data and not self.db.get(Major, data["major_id"]):
            raise NotFound(f"专业不存在（id={data['major_id']}）")
        cid = data.get("counselor_id")
        if cid and not self.db.get(Teacher, cid):
            raise NotFound(f"辅导员不存在（id={cid}）")

    def validate_delete(self, obj: Class) -> None:
        n = self.db.execute(
            select(func.count()).select_from(Student).where(Student.class_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该班级下还有 {n} 名学生，无法删除")


class ClassroomService(BaseCrudService[Classroom]):
    model = Classroom
    search_fields = ("code", "building")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "教室"

    def validate_delete(self, obj: Classroom) -> None:
        n = self.db.execute(
            select(func.count())
            .select_from(Schedule)
            .where(Schedule.classroom_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该教室已被 {n} 条排课占用，无法删除")
