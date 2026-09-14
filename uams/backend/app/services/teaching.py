"""开课与排课业务逻辑。

排课冲突检测是本模块的核心：DATABASE.md §7.3 定义的判定规则
无法用唯一约束表达，必须在这里实现，且排课与选课共用同一套逻辑，
避免两处规则不一致。
"""

from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.models.course import Course
from app.models.organization import Classroom, College
from app.models.person import Teacher
from app.models.teaching import Schedule, TeachingClass, TeachingTask, WeekType
from app.services.base import BaseCrudService


def _period_week_overlap_clause(
    semester: str,
    day_of_week: int,
    start_period: int,
    end_period: int,
    start_week: int,
    end_week: int,
    week_type: str,
):
    """构造"与给定时段冲突"的 SQL 条件（DATABASE.md §7.3）。"""
    conds = [
        Schedule.semester == semester,
        Schedule.day_of_week == day_of_week,
        # 节次区间重叠
        Schedule.start_period <= end_period,
        Schedule.end_period >= start_period,
        # 周次区间重叠
        Schedule.start_week <= end_week,
        Schedule.end_week >= start_week,
    ]
    # 单双周相容：任一为 ALL，或两者相同
    if week_type != WeekType.ALL:
        conds.append(
            or_(Schedule.week_type == WeekType.ALL, Schedule.week_type == week_type)
        )
    return and_(*conds)


class ConflictChecker:
    """排课/选课冲突检测。"""

    def __init__(self, db: Session):
        self.db = db

    def _base(self, sched: dict[str, Any]) -> Select:
        return select(Schedule).where(
            _period_week_overlap_clause(
                sched["semester"],
                sched["day_of_week"],
                sched["start_period"],
                sched["end_period"],
                sched["start_week"],
                sched["end_week"],
                sched["week_type"],
            )
        )

    def classroom_conflict(
        self, sched: dict[str, Any], exclude_schedule_id: int | None = None
    ) -> Schedule | None:
        stmt = self._base(sched).where(Schedule.classroom_id == sched["classroom_id"])
        if exclude_schedule_id:
            stmt = stmt.where(Schedule.id != exclude_schedule_id)
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()

    def teacher_conflict(
        self,
        sched: dict[str, Any],
        teacher_id: int | None,
        exclude_schedule_id: int | None = None,
    ) -> Schedule | None:
        if teacher_id is None:
            return None
        stmt = (
            self._base(sched)
            .join(TeachingClass, Schedule.teaching_class_id == TeachingClass.id)
            .where(
                TeachingClass.teacher_id == teacher_id,
                TeachingClass.status == "ACTIVE",
            )
        )
        if exclude_schedule_id:
            stmt = stmt.where(Schedule.id != exclude_schedule_id)
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()

    def student_conflict(
        self, student_id: int, teaching_class_id: int, semester: str
    ) -> Schedule | None:
        """检查学生已选课程与目标教学班是否时间冲突（选课时调用）。"""
        from app.models.selection import CourseSelection, SelectionState

        targets = list(
            self.db.execute(
                select(Schedule).where(Schedule.teaching_class_id == teaching_class_id)
            ).scalars()
        )
        if not targets:
            return None

        # 学生本学期已选的全部排课
        owned = list(
            self.db.execute(
                select(Schedule)
                .join(TeachingClass, Schedule.teaching_class_id == TeachingClass.id)
                .join(
                    CourseSelection,
                    CourseSelection.teaching_class_id == TeachingClass.id,
                )
                .where(
                    CourseSelection.student_id == student_id,
                    CourseSelection.status == SelectionState.SELECTED,
                    CourseSelection.semester == semester,
                )
            ).scalars()
        )
        for t in targets:
            for o in owned:
                if t.overlaps(o):
                    return o
        return None


class TeachingTaskService(BaseCrudService[TeachingTask]):
    model = TeachingTask
    unique_fields = ()
    default_order = "id"
    entity_name = "教学任务"

    def base_stmt(self) -> Select:
        return select(TeachingTask).options(
            selectinload(TeachingTask.course), selectinload(TeachingTask.college)
        )

    def validate_create(self, data: dict[str, Any]) -> None:
        if not self.db.get(Course, data["course_id"]):
            raise NotFound(f"课程不存在（id={data['course_id']}）")
        if not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")
        if self.db.execute(
            select(TeachingTask).where(
                TeachingTask.semester == data["semester"],
                TeachingTask.course_id == data["course_id"],
                TeachingTask.college_id == data["college_id"],
            )
        ).scalar_one_or_none():
            raise Conflict("该学期该课程的教学任务已存在")

    def validate_delete(self, obj: TeachingTask) -> None:
        n = self.db.execute(
            select(func.count())
            .select_from(TeachingClass)
            .where(TeachingClass.task_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该任务下有 {n} 个教学班，无法删除")

    def class_count(self, task_id: int) -> int:
        return (
            self.db.execute(
                select(func.count())
                .select_from(TeachingClass)
                .where(TeachingClass.task_id == task_id)
            ).scalar()
            or 0
        )


class TeachingClassService(BaseCrudService[TeachingClass]):
    model = TeachingClass
    search_fields = ("code",)
    unique_fields = ("code",)
    default_order = "code"
    entity_name = "教学班"

    def base_stmt(self) -> Select:
        return select(TeachingClass).options(
            selectinload(TeachingClass.course),
            selectinload(TeachingClass.teacher).selectinload(Teacher.user),
            selectinload(TeachingClass.schedules).selectinload(Schedule.classroom),
        )

    def create_class(self, data: dict[str, Any]) -> TeachingClass:
        task = self.db.get(TeachingTask, data["task_id"])
        if task is None:
            raise NotFound(f"教学任务不存在（id={data['task_id']}）")
        if data.get("teacher_id") and not self.db.get(Teacher, data["teacher_id"]):
            raise NotFound(f"教师不存在（id={data['teacher_id']}）")
        self._check_unique({"code": data["code"]})

        obj = TeachingClass(
            code=data["code"],
            task_id=task.id,
            # course_id / semester 从任务带入，保持冗余字段一致（DATABASE.md §13.3）
            course_id=task.course_id,
            semester=task.semester,
            teacher_id=data.get("teacher_id"),
            capacity=data["capacity"],
        )
        self.db.add(obj)
        self._commit()
        return obj

    def update_class(self, class_id: int, data: dict[str, Any]) -> TeachingClass:
        tc = self.get_or_404(class_id)
        data = {k: v for k, v in data.items() if v is not None}

        if "teacher_id" in data:
            if not self.db.get(Teacher, data["teacher_id"]):
                raise NotFound(f"教师不存在（id={data['teacher_id']}）")
            # 换教师需重新检查其所有排课是否冲突
            for s in tc.schedules:
                hit = ConflictChecker(self.db).teacher_conflict(
                    self._sched_dict(s), data["teacher_id"], exclude_schedule_id=s.id
                )
                if hit:
                    raise Conflict(
                        f"该教师在 周{s.day_of_week} 第{s.start_period}-{s.end_period}节 已有其他授课安排"
                    )

        if "capacity" in data and data["capacity"] < tc.selected_count:
            raise Conflict(
                f"容量不能小于已选人数（已选 {tc.selected_count}）"
            )

        for k, v in data.items():
            setattr(tc, k, v)
        self._commit()
        return tc

    def validate_delete(self, obj: TeachingClass) -> None:
        if obj.selected_count > 0:
            raise Conflict(f"该教学班已有 {obj.selected_count} 人选课，无法删除")

    @staticmethod
    def _sched_dict(s: Schedule) -> dict[str, Any]:
        return {
            "semester": s.semester,
            "day_of_week": s.day_of_week,
            "start_period": s.start_period,
            "end_period": s.end_period,
            "start_week": s.start_week,
            "end_week": s.end_week,
            "week_type": s.week_type,
            "classroom_id": s.classroom_id,
        }

    # --- 排课 ---

    def add_schedule(self, class_id: int, data: dict[str, Any]) -> Schedule:
        tc = self.get_or_404(class_id)
        room = self.db.get(Classroom, data["classroom_id"])
        if room is None:
            raise NotFound(f"教室不存在（id={data['classroom_id']}）")
        if room.status != "ACTIVE":
            raise Conflict(f"教室 {room.code} 当前不可用（{room.status}）")
        if room.capacity < tc.capacity:
            raise Conflict(
                f"教室容量 {room.capacity} 小于教学班容量 {tc.capacity}"
            )

        sched = {**data, "semester": tc.semester}
        checker = ConflictChecker(self.db)

        hit = checker.classroom_conflict(sched)
        if hit:
            other = self.db.get(TeachingClass, hit.teaching_class_id)
            raise Conflict(
                f"教室冲突：{room.code} 在该时段已被 {other.code if other else '其他教学班'} 占用"
            )

        hit = checker.teacher_conflict(sched, tc.teacher_id)
        if hit:
            other = self.db.get(TeachingClass, hit.teaching_class_id)
            raise Conflict(
                f"教师冲突：该教师在该时段已有 {other.code if other else '其他'} 的课"
            )

        obj = Schedule(teaching_class_id=tc.id, semester=tc.semester, **data)
        self.db.add(obj)
        self._commit()
        return obj

    def remove_schedule(self, class_id: int, schedule_id: int) -> None:
        s = self.db.get(Schedule, schedule_id)
        if s is None or s.teaching_class_id != class_id:
            raise NotFound("排课不存在")
        self.db.delete(s)
        self._commit()

    def open_selection(self, class_id: int, open_: bool) -> TeachingClass:
        tc = self.get_or_404(class_id)
        if open_ and not tc.teacher_id:
            raise Conflict("尚未分配授课教师，无法开放选课")
        if open_ and not tc.schedules:
            raise Conflict("尚未安排上课时间，无法开放选课")
        tc.selection_status = "OPEN" if open_ else "CLOSED"
        self._commit()
        return tc
