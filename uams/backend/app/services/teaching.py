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
    TeachingScheduleClassConflict,
    TeachingScheduleClassroomConflict,
    TeachingScheduleTeacherConflict,
    TeachingScheduleTermEnded,
)
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.misc import OperationLog
from app.models.organization import Classroom, College
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionSource, SelectionState
from app.models.teaching import Schedule, TeachingClass, TeachingTask, WeekType
from app.models.term import AcademicTerm, TermStatus
from app.models.user import User, UserType
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


def _in_week(s: Schedule, week: int | None) -> bool:
    """该排课是否落在第 ``week`` 周（含单双周判断）；``week`` 为空表示不过滤。

    与 ``api/v1/schedule.py::_in_week`` 同一判定；FIX-007 起教师/学生课表统一走
    ``/teaching-schedules/mine|my``，周次过滤在服务端完成，前端不重复实现。
    """
    if week is None:
        return True
    if not (s.start_week <= week <= s.end_week):
        return False
    if s.week_type == WeekType.ODD:
        return week % 2 == 1
    if s.week_type == WeekType.EVEN:
        return week % 2 == 0
    return True


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

    def class_conflict(
        self,
        sched: dict[str, Any],
        teaching_class_id: int,
        exclude_schedule_id: int | None = None,
    ) -> Schedule | None:
        """同一教学班自身是否已有时间重叠的安排（TASK-013）。"""
        stmt = self._base(sched).where(
            Schedule.teaching_class_id == teaching_class_id
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

    @staticmethod
    def _selection_count_stmt(teaching_class_id: int) -> Select:
        return (
            select(func.count())
            .select_from(CourseSelection)
            .where(
                CourseSelection.teaching_class_id == teaching_class_id,
                CourseSelection.status == SelectionState.SELECTED,
            )
        )

    def selection_count(self, teaching_class_id: int) -> int:
        """已选人数 = COUNT(CourseSelection)，不再持久化（TASK-013）。"""
        return (
            self.db.execute(
                self._selection_count_stmt(teaching_class_id)
            ).scalar()
            or 0
        )

    def selection_counts(self, teaching_class_ids: list[int]) -> dict[int, int]:
        """批量统计已选人数，避免列表场景 N+1。"""
        if not teaching_class_ids:
            return {}
        rows = self.db.execute(
            select(
                CourseSelection.teaching_class_id, func.count()
            )
            .where(
                CourseSelection.teaching_class_id.in_(teaching_class_ids),
                CourseSelection.status == SelectionState.SELECTED,
            )
            .group_by(CourseSelection.teaching_class_id)
        ).all()
        return {tid: cnt for tid, cnt in rows}

    def locked_selection_count(self, teaching_class_id: int) -> int:
        """锁定读取已选人数（当前读），用于持有 TeachingClass 行锁后的容量校验。

        REPEATABLE READ 下普通 COUNT 会读取事务建立时的旧快照（调用方可能先加载了
        Student/User），必须用锁定读才能看到其他事务刚提交的选课记录（TASK-013）。
        """
        rows = self.db.execute(
            select(CourseSelection.id)
            .where(
                CourseSelection.teaching_class_id == teaching_class_id,
                CourseSelection.status == SelectionState.SELECTED,
            )
            .with_for_update()
        ).scalars().all()
        return len(rows)

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

        if "capacity" in data:
            enrolled = self.selection_count(tc.id)
            if data["capacity"] < enrolled:
                raise CapacityBelowEnrolled(
                    f"容量不能小于已选人数（已选 {enrolled}）"
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
        """教学班下新增排课（委托 ScheduleService，TASK-013）。"""
        return ScheduleService(self.db).create({**data, "teaching_class_id": class_id})

    def update_schedule(self, class_id: int, schedule_id: int, data: dict[str, Any]) -> Schedule:
        """修改教学班下的排课（TASK-013）。"""
        s = ScheduleService(self.db).get_or_404(schedule_id)
        if s.teaching_class_id != class_id:
            raise NotFound("排课不存在")
        return ScheduleService(self.db).update(schedule_id, data)

    def remove_schedule(self, class_id: int, schedule_id: int) -> None:
        """删除教学班下的排课（TASK-013）。"""
        s = ScheduleService(self.db).get_or_404(schedule_id)
        if s.teaching_class_id != class_id:
            raise NotFound("排课不存在")
        ScheduleService(self.db).delete(schedule_id)

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

    def _log_selection_action(
        self,
        operator: User | None,
        action: str,
        tc: TeachingClass,
        student: Student,
        detail: str,
    ) -> None:
        self.db.add(
            OperationLog(
                user_id=operator.id if operator else None,
                username=operator.username if operator else None,
                action=action,
                module="selection",
                resource_type="teaching_class",
                resource_id=tc.id,
                detail=detail[:500],
                result="SUCCESS",
            )
        )

    def add_student(
        self,
        class_id: int,
        student_id: int,
        operator: User | None = None,
    ) -> CourseSelection:
        """教务手动将学生加入教学班（FIX-002）。

        管理员手动添加也必须经过容量、学期、学籍、同课程与时间冲突校验，
        不能因为拥有 selection:manage 权限而绕过业务规则。
        """
        # 行级锁：与选课/批量预排一致，防止并发下超容。
        tc = self.db.execute(
            select(TeachingClass).where(TeachingClass.id == class_id).with_for_update()
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={class_id}）")
        if tc.status != "ACTIVE":
            raise Conflict("该教学班已取消，无法添加学生")
        if tc.term is None or tc.term.status != TermStatus.ACTIVE:
            raise Conflict("当前学期未在进行中，无法添加学生")
        if tc.teacher_id is None:
            raise Conflict("尚未分配授课教师，无法添加学生")
        if not tc.schedules:
            raise Conflict("尚未安排上课时间，无法添加学生")

        student = self.db.get(Student, student_id)
        if student is None:
            raise NotFound(f"学生不存在（id={student_id}）")
        if student.academic_status != "ENROLLED":
            raise Conflict(
                f"学生学籍状态为 {student.academic_status}，无法加入教学班"
            )

        sel = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student_id,
                CourseSelection.teaching_class_id == class_id,
            )
        ).scalar_one_or_none()
        if sel is not None and sel.status == SelectionState.SELECTED:
            raise Conflict("该学生已在此教学班中")

        same_course = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student_id,
                CourseSelection.course_id == tc.course_id,
                CourseSelection.semester == tc.semester,
                CourseSelection.status == SelectionState.SELECTED,
                CourseSelection.teaching_class_id != tc.id,
            ).limit(1)
        ).scalar_one_or_none()
        if same_course is not None:
            raise Conflict("该学生已选同一课程的其他教学班，不能重复添加")

        hit = ConflictChecker(self.db).student_conflict(
            student_id, class_id, tc.semester
        )
        if hit is not None:
            other = self.db.get(TeachingClass, hit.teaching_class_id)
            raise Conflict(
                f"时间冲突：与 {other.code if other else '已选课程'} 的排课冲突"
            )

        # 容量约束（TASK-012/013）：已选人数由 CourseSelection 动态统计，不得超容。
        enrolled = self.locked_selection_count(class_id)
        if enrolled >= tc.capacity:
            raise TeachingClassFull(f"该教学班已满（{enrolled}/{tc.capacity}）")

        now = datetime.now()
        if sel is not None:  # 曾退课，手动添加复用该行
            sel.status = SelectionState.SELECTED
            sel.selected_at = now
            sel.dropped_at = None
            sel.source = SelectionSource.ADMIN_MANUAL
        else:
            sel = CourseSelection(
                student_id=student_id,
                teaching_class_id=class_id,
                course_id=tc.course_id,
                semester=tc.semester,
                status=SelectionState.SELECTED,
                source=SelectionSource.ADMIN_MANUAL,
                selected_at=now,
            )
            self.db.add(sel)

        self._log_selection_action(
            operator,
            "ADMIN_ADD_STUDENT",
            tc,
            student,
            f"教务手动添加学生 {student.student_no} 到教学班 {tc.code}",
        )
        self._commit()
        return sel

    def remove_student(
        self,
        class_id: int,
        student_id: int,
        operator: User | None = None,
    ) -> None:
        """教务手动将学生从教学班移除（FIX-002）。

        已有成绩记录时拒绝移除，避免留下没有选课归属的成绩。
        """
        tc = self.db.execute(
            select(TeachingClass).where(TeachingClass.id == class_id).with_for_update()
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={class_id}）")
        if tc.term is None or tc.term.status != TermStatus.ACTIVE:
            raise Conflict("当前学期未在进行中，无法移除学生")

        student = self.db.get(Student, student_id)
        if student is None:
            raise NotFound(f"学生不存在（id={student_id}）")
        sel = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student_id,
                CourseSelection.teaching_class_id == class_id,
            )
        ).scalar_one_or_none()
        if sel is None or sel.status != SelectionState.SELECTED:
            raise NotFound("该学生不在此教学班中")

        grade = self.db.execute(
            select(Grade.id)
            .where(
                Grade.student_id == student_id,
                Grade.teaching_class_id == class_id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if grade is not None:
            raise Conflict("该学生已有成绩记录，无法移除；如确需调整请先处理成绩")

        sel.status = SelectionState.DROPPED
        sel.dropped_at = datetime.now()
        self._log_selection_action(
            operator,
            "ADMIN_REMOVE_STUDENT",
            tc,
            student,
            f"教务从教学班 {tc.code} 移除学生 {student.student_no}",
        )
        self._commit()


class ScheduleService:
    """教学安排（排课）业务逻辑（TASK-013）。

    复用既有 ``Schedule`` 模型（`schedules` 表）作为教学安排实体；
    一个教学班可有多条安排，冲突检测统一走 :class:`ConflictChecker`。
    """

    entity_name = "教学安排"

    def __init__(self, db: Session):
        self.db = db

    def base_stmt(self) -> Select:
        return select(Schedule).options(
            selectinload(Schedule.teaching_class).selectinload(TeachingClass.course),
            selectinload(Schedule.teaching_class)
            .selectinload(TeachingClass.teacher)
            .selectinload(Teacher.user),
            selectinload(Schedule.teaching_class).selectinload(TeachingClass.term),
            selectinload(Schedule.classroom),
        )

    def get_or_404(self, schedule_id: int) -> Schedule:
        row = self.db.execute(
            self.base_stmt().where(Schedule.id == schedule_id)
        ).scalar_one_or_none()
        if row is None:
            raise NotFound(f"{self.entity_name}不存在（id={schedule_id}）")
        return row

    @staticmethod
    def _term_guard(tc: TeachingClass) -> None:
        if tc.term is not None and tc.term.status == TermStatus.ENDED:
            raise TeachingScheduleTermEnded("该学期已结束，不能操作教学安排")

    def _room_guard(self, classroom_id: int, tc: TeachingClass) -> None:
        room = self.db.get(Classroom, classroom_id)
        if room is None:
            raise NotFound(f"教室不存在（id={classroom_id}）")
        if room.status != "ACTIVE":
            raise Conflict(f"教室 {room.code} 当前不可用（{room.status}）")
        if room.capacity < tc.capacity:
            raise Conflict(f"教室容量 {room.capacity} 小于教学班容量 {tc.capacity}")

    @staticmethod
    def _sched_dict(tc: TeachingClass, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "semester": tc.semester,
            "day_of_week": data["day_of_week"],
            "start_period": data["start_period"],
            "end_period": data["end_period"],
            "start_week": data["start_week"],
            "end_week": data["end_week"],
            "week_type": data.get("week_type", WeekType.ALL),
            "classroom_id": data["classroom_id"],
        }

    def _check_conflicts(
        self,
        sched: dict[str, Any],
        tc: TeachingClass,
        exclude_schedule_id: int | None = None,
    ) -> None:
        """三类冲突检测：教学班自身 → 教室 → 教师（TASK-013 §8）。"""
        checker = ConflictChecker(self.db)
        hit = checker.class_conflict(sched, tc.id, exclude_schedule_id)
        if hit:
            raise TeachingScheduleClassConflict(
                f"该教学班在 周{sched['day_of_week']} "
                f"第{sched['start_period']}-{sched['end_period']}节 已有其他安排"
            )
        hit = checker.classroom_conflict(sched, exclude_schedule_id)
        if hit:
            raise TeachingScheduleClassroomConflict(
                f"教室在该时段已被其他教学班占用"
            )
        hit = checker.teacher_conflict(sched, tc.teacher_id, exclude_schedule_id)
        if hit:
            raise TeachingScheduleTeacherConflict(
                f"该教师在该时段已有其他教学安排"
            )

    def create(self, data: dict[str, Any]) -> Schedule:
        tc = self.db.get(TeachingClass, data["teaching_class_id"])
        if tc is None:
            raise NotFound(f"教学班不存在（id={data['teaching_class_id']}）")
        self._term_guard(tc)
        self._room_guard(data["classroom_id"], tc)

        sched = self._sched_dict(tc, data)
        self._check_conflicts(sched, tc)

        obj = Schedule(
            teaching_class_id=tc.id,
            semester=tc.semester,
            classroom_id=data["classroom_id"],
            day_of_week=data["day_of_week"],
            start_period=data["start_period"],
            end_period=data["end_period"],
            start_week=data["start_week"],
            end_week=data["end_week"],
            week_type=data.get("week_type", WeekType.ALL),
        )
        self.db.add(obj)
        self.db.commit()
        return obj

    def update(self, schedule_id: int, data: dict[str, Any]) -> Schedule:
        s = self.get_or_404(schedule_id)
        tc = s.teaching_class
        self._term_guard(tc)

        # teaching_class_id 不可变：换教学班应删除后重建（TASK-013 §14）
        if "teaching_class_id" in data and data["teaching_class_id"] != tc.id:
            raise Conflict("教学安排所属教学班不可修改，请删除后重建")

        merged = {
            "day_of_week": data.get("day_of_week", s.day_of_week),
            "start_period": data.get("start_period", s.start_period),
            "end_period": data.get("end_period", s.end_period),
            "start_week": data.get("start_week", s.start_week),
            "end_week": data.get("end_week", s.end_week),
            "week_type": data.get("week_type", s.week_type),
            "classroom_id": data.get("classroom_id", s.classroom_id),
        }
        # 合并后校验区间（节次/周次）
        if merged["end_period"] < merged["start_period"]:
            raise Conflict("结束节次不能早于开始节次")
        if merged["end_week"] < merged["start_week"]:
            raise Conflict("结束周不能早于开始周")
        if "classroom_id" in data:
            self._room_guard(merged["classroom_id"], tc)

        sched = self._sched_dict(tc, merged)
        self._check_conflicts(sched, tc, exclude_schedule_id=s.id)

        for k, v in merged.items():
            setattr(s, k, v)
        self.db.commit()
        return s

    def delete(self, schedule_id: int) -> None:
        s = self.get_or_404(schedule_id)
        self._term_guard(s.teaching_class)
        self.db.delete(s)
        self.db.commit()

    def list(
        self,
        *,
        term_id: int | None = None,
        teaching_class_id: int | None = None,
        teacher_id: int | None = None,
        weekday: int | None = None,
        classroom: str | None = None,
    ) -> list[Schedule]:
        """教务处查询全部教学安排，过滤条件均在数据库层完成（TASK-013 §18）。"""
        stmt = self.base_stmt()
        if teaching_class_id is not None:
            stmt = stmt.where(Schedule.teaching_class_id == teaching_class_id)
        if term_id is not None or teacher_id is not None:
            tc_ids = select(TeachingClass.id)
            if term_id is not None:
                tc_ids = tc_ids.where(TeachingClass.term_id == term_id)
            if teacher_id is not None:
                tc_ids = tc_ids.where(TeachingClass.teacher_id == teacher_id)
            stmt = stmt.where(Schedule.teaching_class_id.in_(tc_ids))
        if weekday is not None:
            stmt = stmt.where(Schedule.day_of_week == weekday)
        if classroom is not None:
            room_ids = select(Classroom.id).where(Classroom.code == classroom)
            stmt = stmt.where(Schedule.classroom_id.in_(room_ids))
        stmt = stmt.order_by(
            Schedule.day_of_week, Schedule.start_period, Schedule.start_week
        )
        return list(self.db.execute(stmt).scalars())

    def mine_for_teacher(
        self,
        teacher_id: int,
        term_id: int | None = None,
        semester: str | None = None,
        week: int | None = None,
    ) -> list[Schedule]:
        """教师本人教学班的教学安排（身份取自 token，不接受 teacher_id）。

        FIX-007：补可选 ``semester``（字符串学期，前端课表选择器直接用）与 ``week``
        （第几周，含单双周相容判断），使教师课表可完全走本接口，不必再依赖旧课表接口。
        """
        tc_ids = select(TeachingClass.id).where(TeachingClass.teacher_id == teacher_id)
        if term_id is not None:
            tc_ids = tc_ids.where(TeachingClass.term_id == term_id)
        if semester is not None:
            tc_ids = tc_ids.where(TeachingClass.semester == semester)
        stmt = (
            self.base_stmt()
            .where(Schedule.teaching_class_id.in_(tc_ids))
            .order_by(Schedule.day_of_week, Schedule.start_period, Schedule.start_week)
        )
        rows = list(self.db.execute(stmt).scalars())
        return [s for s in rows if _in_week(s, week)]

    def mine_for_student(
        self,
        student_id: int,
        term_id: int | None = None,
        semester: str | None = None,
        week: int | None = None,
    ) -> list[Schedule]:
        """学生本人已选教学班的教学安排；未选课返回空列表而非 404（TASK-013 §17）。

        FIX-007：同样补可选 ``semester`` / ``week``，见 ``mine_for_teacher``。
        """
        sel_tc = (
            select(CourseSelection.teaching_class_id)
            .join(
                TeachingClass,
                CourseSelection.teaching_class_id == TeachingClass.id,
            )
            .where(
                CourseSelection.student_id == student_id,
                CourseSelection.status == SelectionState.SELECTED,
            )
        )
        if term_id is not None:
            sel_tc = sel_tc.where(TeachingClass.term_id == term_id)
        if semester is not None:
            sel_tc = sel_tc.where(TeachingClass.semester == semester)
        stmt = (
            self.base_stmt()
            .where(Schedule.teaching_class_id.in_(sel_tc))
            .order_by(Schedule.day_of_week, Schedule.start_period, Schedule.start_week)
        )
        rows = list(self.db.execute(stmt).scalars())
        return [s for s in rows if _in_week(s, week)]
