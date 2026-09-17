"""开课与排课业务逻辑。

排课冲突检测是本模块的核心：DATABASE.md §7.3 定义的判定规则
无法用唯一约束表达，必须在这里实现，且排课与选课共用同一套逻辑，
避免两处规则不一致。
"""

from typing import Any

from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    CapacityBelowEnrolled,
    Conflict,
    NotFound,
    TeachingClassCourseImmutable,
    TeachingClassFull,
    TeachingClassHasData,
    TeachingClassTeacherLocked,
    TeachingClassTermEnded,
    TeachingClassTermImmutable,
)
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Classroom, College
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass, TeachingTask, WeekType
from app.models.term import AcademicTerm, TermStatus
from app.models.user import UserType
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
    # 唯一性已改为 (term_id, code) 复合唯一，由 _check_term_code_unique 手工校验
    unique_fields = ()
    default_order = "code"
    entity_name = "教学班"

    def base_stmt(self) -> Select:
        return select(TeachingClass).options(
            selectinload(TeachingClass.course),
            selectinload(TeachingClass.term),
            selectinload(TeachingClass.teacher).selectinload(Teacher.user),
            selectinload(TeachingClass.schedules).selectinload(Schedule.classroom),
        )

    def my_classes(
        self, teacher_id: int, semester: str | None = None, term_id: int | None = None
    ) -> list[TeachingClass]:
        """教师本人授课的教学班列表（TASK-005，后端强制按 token 身份过滤）。"""
        stmt = self.base_stmt().where(TeachingClass.teacher_id == teacher_id)
        if semester:
            stmt = stmt.where(TeachingClass.semester == semester)
        if term_id:
            stmt = stmt.where(TeachingClass.term_id == term_id)
        return list(self.db.execute(stmt.order_by(TeachingClass.course_id)).scalars())

    def _check_term_code_unique(self, term_id: int, code: str) -> None:
        """教学班编号仅在同一学期内唯一（TASK-011）。"""
        if self.db.execute(
            select(TeachingClass).where(
                TeachingClass.term_id == term_id,
                TeachingClass.code == code,
            )
        ).first():
            raise Conflict(f"该学期下教学班编号已存在：{code}")

    def create_class(self, data: dict[str, Any]) -> TeachingClass:
        task = self.db.get(TeachingTask, data["task_id"])
        if task is None:
            raise NotFound(f"教学任务不存在（id={data['task_id']}）")
        if self.db.get(Course, task.course_id) is None:
            raise NotFound(f"课程不存在（id={task.course_id}）")

        # 学期校验（TASK-011）：必须指定学期，且已结束的学期不能创建教学班
        term = self.db.get(AcademicTerm, data["term_id"])
        if term is None:
            raise NotFound(f"学期不存在（id={data['term_id']}）")
        if term.status == TermStatus.ENDED:
            raise TeachingClassTermEnded("已结束的学期不能创建教学班")

        # 授课教师（TASK-012）：必须指定，且必须具有教师身份
        teacher_id = data["teacher_id"]
        teacher = self.db.get(Teacher, teacher_id)
        if teacher is None:
            raise NotFound(f"教师不存在（id={teacher_id}）")
        if teacher.user is None or teacher.user.user_type != UserType.TEACHER:
            raise Conflict("授课教师必须具有教师身份")

        self._check_term_code_unique(data["term_id"], data["code"])

        obj = TeachingClass(
            code=data["code"],
            name=data.get("name"),
            task_id=task.id,
            term_id=data["term_id"],
            # course_id / semester 从任务带入，保持冗余字段一致（DATABASE.md §13.3）
            course_id=task.course_id,
            semester=task.semester,
            teacher_id=teacher_id,
            capacity=data["capacity"],
        )
        self.db.add(obj)
        self._commit()
        return obj

    def update_class(self, class_id: int, data: dict[str, Any]) -> TeachingClass:
        tc = self.get_or_404(class_id)
        data = {k: v for k, v in data.items() if v is not None}

        # 不可变字段保护（TASK-012）：term_id / course_id 一经创建不可修改
        if "term_id" in data:
            raise TeachingClassTermImmutable("教学班所属学期不可修改")
        if "course_id" in data:
            raise TeachingClassCourseImmutable("教学班所属课程不可修改")

        # 已结束学期只读（TASK-012）
        if tc.term is not None and tc.term.status == TermStatus.ENDED:
            raise TeachingClassTermEnded("已结束的学期不能修改教学班")

        # 更换教师（TASK-012）：校验身份、成绩锁定、排课冲突
        if "teacher_id" in data and data["teacher_id"] != tc.teacher_id:
            teacher = self.db.get(Teacher, data["teacher_id"])
            if teacher is None:
                raise NotFound(f"教师不存在（id={data['teacher_id']}）")
            if teacher.user is None or teacher.user.user_type != UserType.TEACHER:
                raise Conflict("授课教师必须具有教师身份")
            # 已有成绩提交/审核后，锁定教师不可更换
            locked = self.db.execute(
                select(Grade.id)
                .where(
                    Grade.teaching_class_id == tc.id,
                    Grade.status.in_((GradeStatus.SUBMITTED, GradeStatus.APPROVED)),
                )
                .limit(1)
            ).scalar_one_or_none()
            if locked:
                raise TeachingClassTeacherLocked(
                    "该教学班已有成绩提交或审核，无法更换教师"
                )
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
            raise CapacityBelowEnrolled(
                f"容量不能小于已选人数（已选 {tc.selected_count}）"
            )

        for k, v in data.items():
            setattr(tc, k, v)
        self._commit()
        return tc

    def validate_delete(self, obj: TeachingClass) -> None:
        # 已结束学期只读（TASK-012）
        if obj.term is not None and obj.term.status == TermStatus.ENDED:
            raise TeachingClassTermEnded("已结束的学期不能删除教学班")
        # 仅空教学班可删除：无选课记录且无成绩记录（TASK-012）
        has_selection = self.db.execute(
            select(CourseSelection.id)
            .where(
                CourseSelection.teaching_class_id == obj.id,
                CourseSelection.status == SelectionState.SELECTED,
            )
            .limit(1)
        ).scalar_one_or_none()
        if has_selection:
            raise TeachingClassHasData("该教学班已有学生选课，无法删除")
        has_grade = self.db.execute(
            select(Grade.id).where(Grade.teaching_class_id == obj.id).limit(1)
        ).scalar_one_or_none()
        if has_grade:
            raise TeachingClassHasData("该教学班已有成绩记录，无法删除")

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

    # --- 学生归属管理（TASK-008，仅教务处） ---

    def add_student(self, class_id: int, student_id: int) -> CourseSelection:
        """教务处将学生加入教学班。仅建立归属关系，但遵守容量约束（TASK-012）。"""
        # 行级锁：与选课一致，防止并发下超容（CLAUDE.md §20）
        tc = self.db.execute(
            select(TeachingClass).where(TeachingClass.id == class_id).with_for_update()
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={class_id}）")
        if tc.status != "ACTIVE":
            raise Conflict("该教学班已取消，无法添加学生")
        if self.db.get(Student, student_id) is None:
            raise NotFound(f"学生不存在（id={student_id}）")

        sel = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student_id,
                CourseSelection.teaching_class_id == class_id,
            )
        ).scalar_one_or_none()
        if sel is not None and sel.status == SelectionState.SELECTED:
            raise Conflict("该学生已在此教学班中")

        # 容量约束（TASK-012）：教务处添加同样不得超容
        if tc.selected_count >= tc.capacity:
            raise TeachingClassFull(f"该教学班已满（{tc.selected_count}/{tc.capacity}）")

        if sel is not None:  # 曾退课，复用该行
            sel.status = SelectionState.SELECTED
            sel.selected_at = datetime.now()
            sel.dropped_at = None
        else:
            sel = CourseSelection(
                student_id=student_id,
                teaching_class_id=class_id,
                course_id=tc.course_id,
                semester=tc.semester,
            )
            self.db.add(sel)
        tc.selected_count += 1
        self._commit()
        return sel

    def remove_student(self, class_id: int, student_id: int) -> None:
        """教务处将学生从教学班移除。"""
        tc = self.get_or_404(class_id)
        sel = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student_id,
                CourseSelection.teaching_class_id == class_id,
            )
        ).scalar_one_or_none()
        if sel is None or sel.status != SelectionState.SELECTED:
            raise NotFound("该学生不在此教学班中")
        sel.status = SelectionState.DROPPED
        sel.dropped_at = datetime.now()
        tc.selected_count = max(0, tc.selected_count - 1)
        self._commit()
