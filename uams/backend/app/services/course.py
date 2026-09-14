"""课程与培养方案业务逻辑。"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import Conflict, NotFound
from app.models.course import (
    Course,
    CoursePrerequisite,
    CurriculumCourse,
    CurriculumPlan,
)
from app.models.organization import College, Major
from app.services.base import BaseCrudService


class CourseService(BaseCrudService[Course]):
    model = Course
    search_fields = ("code", "name")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "课程"

    def base_stmt(self) -> Select:
        return select(Course).options(selectinload(Course.college))

    def validate_create(self, data: dict[str, Any]) -> None:
        if not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")

    def validate_update(self, obj: Course, data: dict[str, Any]) -> None:
        if "college_id" in data and not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")

    def validate_delete(self, obj: Course) -> None:
        from app.models.teaching import TeachingTask

        n = self.db.execute(
            select(func.count())
            .select_from(TeachingTask)
            .where(TeachingTask.course_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该课程已有 {n} 个教学任务，无法删除")

    # --- 先修课程 ---

    def list_prerequisites(self, course_id: int) -> list[CoursePrerequisite]:
        self.get_or_404(course_id)
        return list(
            self.db.execute(
                select(CoursePrerequisite).where(
                    CoursePrerequisite.course_id == course_id
                )
            ).scalars()
        )

    def _would_create_cycle(self, course_id: int, prereq_id: int) -> bool:
        """检测先修关系是否形成环路。

        DATABASE.md §6.2：CHECK 只能挡住直接自引用，
        A→B→A 这类环路必须在这里做图遍历检测。
        """
        # 从 prereq 出发，沿"它的先修课"向上走；若能到达 course_id 则成环
        visited: set[int] = set()
        stack = [prereq_id]
        while stack:
            cur = stack.pop()
            if cur == course_id:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            rows = self.db.execute(
                select(CoursePrerequisite.prerequisite_course_id).where(
                    CoursePrerequisite.course_id == cur
                )
            ).scalars()
            stack.extend(rows)
        return False

    def add_prerequisite(
        self, course_id: int, prereq_id: int, min_score
    ) -> CoursePrerequisite:
        self.get_or_404(course_id)
        if not self.db.get(Course, prereq_id):
            raise NotFound(f"先修课程不存在（id={prereq_id}）")
        if course_id == prereq_id:
            raise Conflict("课程不能以自身作为先修课程")
        if self.db.execute(
            select(CoursePrerequisite).where(
                CoursePrerequisite.course_id == course_id,
                CoursePrerequisite.prerequisite_course_id == prereq_id,
            )
        ).scalar_one_or_none():
            raise Conflict("该先修关系已存在")
        if self._would_create_cycle(course_id, prereq_id):
            raise Conflict("该先修关系会形成环路，已拒绝")

        obj = CoursePrerequisite(
            course_id=course_id,
            prerequisite_course_id=prereq_id,
            min_score=min_score,
        )
        self.db.add(obj)
        self._commit()
        return obj

    def remove_prerequisite(self, course_id: int, prereq_row_id: int) -> None:
        obj = self.db.get(CoursePrerequisite, prereq_row_id)
        if obj is None or obj.course_id != course_id:
            raise NotFound("先修关系不存在")
        self.db.delete(obj)
        self._commit()


class CurriculumService(BaseCrudService[CurriculumPlan]):
    model = CurriculumPlan
    search_fields = ("code", "name")
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "培养方案"

    def base_stmt(self) -> Select:
        return select(CurriculumPlan).options(selectinload(CurriculumPlan.major))

    def validate_create(self, data: dict[str, Any]) -> None:
        if not self.db.get(Major, data["major_id"]):
            raise NotFound(f"专业不存在（id={data['major_id']}）")
        if self.db.execute(
            select(CurriculumPlan).where(
                CurriculumPlan.major_id == data["major_id"],
                CurriculumPlan.grade_year == data["grade_year"],
            )
        ).scalar_one_or_none():
            raise Conflict("该专业该年级的培养方案已存在")

    def list_courses(self, plan_id: int) -> list[CurriculumCourse]:
        self.get_or_404(plan_id)
        return list(
            self.db.execute(
                select(CurriculumCourse)
                .options(selectinload(CurriculumCourse.course))
                .where(CurriculumCourse.plan_id == plan_id)
                .order_by(CurriculumCourse.suggested_semester)
            ).scalars()
        )

    def add_course(
        self, plan_id: int, course_id: int, semester: int, is_required: bool
    ) -> CurriculumCourse:
        self.get_or_404(plan_id)
        if not self.db.get(Course, course_id):
            raise NotFound(f"课程不存在（id={course_id}）")
        if self.db.execute(
            select(CurriculumCourse).where(
                CurriculumCourse.plan_id == plan_id,
                CurriculumCourse.course_id == course_id,
            )
        ).scalar_one_or_none():
            raise Conflict("该课程已在培养方案中")
        obj = CurriculumCourse(
            plan_id=plan_id,
            course_id=course_id,
            suggested_semester=semester,
            is_required=is_required,
        )
        self.db.add(obj)
        self._commit()
        return obj

    def remove_course(self, plan_id: int, row_id: int) -> None:
        obj = self.db.get(CurriculumCourse, row_id)
        if obj is None or obj.plan_id != plan_id:
            raise NotFound("方案课程不存在")
        self.db.delete(obj)
        self._commit()
