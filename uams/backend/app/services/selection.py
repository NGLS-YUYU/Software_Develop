"""选课业务逻辑。

这是全系统并发要求最高的模块（CLAUDE.md §19/§20）：
  - 选课必须在单个事务内完成「校验 → 建记录 → 更新计数」
  - 必须用 SELECT ... FOR UPDATE 锁住教学班行，防止超卖
  - 唯一约束 uk_selection 作为最后一道防线
"""

import re
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound, PermissionDenied, TeachingClassFull
from app.models.course import Course, CoursePrerequisite, CourseType
from app.models.grade import Grade, GradeStatus
from app.models.misc import OperationLog
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.selection import (
    CourseSelection,
    SelectionPeriod,
    SelectionSource,
    SelectionState,
)
from app.models.teaching import Schedule, TeachingClass
from app.models.term import AcademicTerm, TermStatus
from app.models.user import User
from app.services.integrity import conflict_from_integrity_error
from app.services.teaching import ConflictChecker

SOURCE_LABELS = {
    SelectionSource.STUDENT: "学生自主选课",
    SelectionSource.ADMIN_REQUIRED: "教务批量预安排",
    SelectionSource.ADMIN_MANUAL: "教务手动添加",
}
REASON_LABELS = {
    "ALREADY_ASSIGNED": "已安排",
    "PREVIOUSLY_REMOVED": "曾从本教学班移除",
    "SAME_COURSE_OTHER_CLASS": "已选同课程其他教学班",
    "TIME_CONFLICT": "课表时间冲突",
    "CAPACITY_FULL": "教学班容量不足",
    "INVALID_STATUS": "学籍状态无效",
}


def selection_source_label(source: str | None) -> str:
    if not source:
        return "历史记录（未标记来源）"
    return SOURCE_LABELS.get(source, source)

# 必修 / 选修分类（TASK-009）：复用 CourseType 枚举，不修改课程类型体系。
# 必修课只能由教务处预排；选修课可由学生自主选择。
_REQUIRED_TYPES = (CourseType.REQUIRED, CourseType.PUBLIC_REQUIRED, CourseType.PRACTICE)
_ELECTIVE_TYPES = (CourseType.ELECTIVE, CourseType.PUBLIC_ELECTIVE)


def _is_required(course_type: str | None) -> bool:
    return course_type in _REQUIRED_TYPES


def _is_elective(course_type: str | None) -> bool:
    return course_type in _ELECTIVE_TYPES


class SelectionService:
    def __init__(self, db: Session):
        self.db = db

    # --- 查询 ---

    def base_stmt(self) -> Select:
        return select(CourseSelection).options(
            selectinload(CourseSelection.course),
            selectinload(CourseSelection.teaching_class).selectinload(
                TeachingClass.teacher
            ).selectinload(Teacher.user),
            selectinload(CourseSelection.teaching_class).selectinload(
                TeachingClass.schedules
            ).selectinload(Schedule.classroom),
        )

    def list_by_student(
        self, student_id: int, semester: str | None = None, include_dropped: bool = False
    ) -> list[CourseSelection]:
        stmt = self.base_stmt().where(CourseSelection.student_id == student_id)
        if semester:
            stmt = stmt.where(CourseSelection.semester == semester)
        if not include_dropped:
            stmt = stmt.where(CourseSelection.status == SelectionState.SELECTED)
        return list(self.db.execute(stmt).scalars())

    def list_by_class(self, teaching_class_id: int) -> list[CourseSelection]:
        stmt = (
            select(CourseSelection)
            .options(
                selectinload(CourseSelection.student).selectinload(Student.user),
                selectinload(CourseSelection.student).selectinload(Student.klass),
                selectinload(CourseSelection.student).selectinload(Student.major),
            )
            .where(
                CourseSelection.teaching_class_id == teaching_class_id,
                CourseSelection.status == SelectionState.SELECTED,
            )
        )
        return list(self.db.execute(stmt).scalars())

    # --- 校验 ---

    @staticmethod
    def _window_payload(period: SelectionPeriod) -> dict:
        return {
            "id": period.id,
            "name": period.name,
            "start_time": period.start_time,
            "end_time": period.end_time,
            "target_grade_year": period.target_grade_year,
            "status": period.status,
        }

    def _term_for_semester(self, semester: str) -> AcademicTerm | None:
        match = re.match(r"^(\d{4}-\d{4})-([12])$", semester or "")
        if match is None:
            return None
        return self.db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == match.group(1),
                AcademicTerm.semester == int(match.group(2)),
            )
        ).scalar_one_or_none()

    def selection_window_status(
        self,
        student: Student,
        semester: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        """统一的选课/退课窗口判断（FIX-003）。

        规则：
          - 学期必须 ACTIVE；
          - 至少一个 status=ACTIVE 且当前时间落在 [start_time, end_time] 内、
            且对学生年级适用的窗口；
          - 同一学期多个适用窗口重叠时按并集处理：任一窗口开放即可；
          - 时间边界包含 start_time / end_time；
          - 使用应用服务器本地时间与 MySQL DATETIME 直接比较，不做时区换算
            （部署环境必须保持同一时区）。
        """
        now = now or datetime.now()
        term = self._term_for_semester(semester)
        periods = list(
            self.db.execute(
                select(SelectionPeriod)
                .where(SelectionPeriod.semester == semester)
                .order_by(SelectionPeriod.start_time, SelectionPeriod.id)
            ).scalars()
        )
        active = [p for p in periods if p.status == "ACTIVE"]
        state = {
            "semester": semester,
            "term_status": term.status if term else None,
            "can_select": False,
            "can_drop": False,
            "reason_code": None,
            "reason": None,
            "window": None,
            "open_windows": [],
        }
        if term is None:
            state.update(reason_code="TERM_NOT_FOUND", reason="该学期不存在")
            return state
        if term.status != TermStatus.ACTIVE:
            state.update(
                reason_code="TERM_NOT_ACTIVE",
                reason=f"该学期状态为 {term.status}，未处于进行中",
            )
            return state
        if not periods:
            state.update(reason_code="NO_PERIOD", reason="本学期尚未设置选课时间")
            return state
        if not active:
            state.update(
                reason_code="NO_ACTIVE_PERIOD",
                reason="选课窗口未开放（没有进行中的窗口）",
            )
            return state

        def grade_ok(p: SelectionPeriod) -> bool:
            return (
                p.target_grade_year is None
                or p.target_grade_year == student.enrollment_year
            )

        open_windows = [
            p
            for p in active
            if grade_ok(p) and p.start_time <= now <= p.end_time
        ]
        if open_windows:
            # 并集语义：多个重叠窗口任一开放即可；展示开始时间最晚的窗口。
            chosen = sorted(open_windows, key=lambda p: (p.start_time, p.id))[-1]
            state.update(
                can_select=True,
                can_drop=True,
                window=self._window_payload(chosen),
                open_windows=[self._window_payload(p) for p in open_windows],
            )
            return state

        eligible = [p for p in active if grade_ok(p)]
        in_time_active = [
            p for p in active if p.start_time <= now <= p.end_time
        ]
        if in_time_active and not eligible:
            state.update(
                reason_code="GRADE_MISMATCH",
                reason="当前选课窗口不适用于你的年级",
            )
            return state
        if eligible:
            if now < min(p.start_time for p in eligible):
                state.update(reason_code="NOT_STARTED", reason="选课尚未开始")
            elif now > max(p.end_time for p in eligible):
                state.update(reason_code="EXPIRED", reason="选课已结束")
            else:
                state.update(reason_code="NOT_OPEN", reason="当前不在选课时间内")
        else:
            if now < min(p.start_time for p in active):
                state.update(reason_code="NOT_STARTED", reason="选课尚未开始")
            elif now > max(p.end_time for p in active):
                state.update(reason_code="EXPIRED", reason="选课已结束")
            else:
                state.update(
                    reason_code="GRADE_MISMATCH",
                    reason="当前选课窗口不适用于你的年级",
                )
        return state

    def _check_selection_window(self, student: Student, semester: str) -> None:
        state = self.selection_window_status(student, semester)
        if not state["can_select"]:
            raise Conflict(state["reason"] or "当前不在选课时间内")

    def _check_prerequisites(self, student_id: int, course_id: int) -> None:
        """先修课程校验（PRD §7.2）。"""
        prereqs = list(
            self.db.execute(
                select(CoursePrerequisite).where(
                    CoursePrerequisite.course_id == course_id
                )
            ).scalars()
        )
        for p in prereqs:
            g = self.db.execute(
                select(Grade).where(
                    Grade.student_id == student_id,
                    Grade.course_id == p.prerequisite_course_id,
                    Grade.status == GradeStatus.APPROVED,
                )
            ).scalars().first()
            if g is None or g.total_score is None:
                raise Conflict("未修读先修课程，无法选课")
            if Decimal(str(g.total_score)) < Decimal(str(p.min_score)):
                raise Conflict(
                    f"先修课程成绩 {g.total_score} 未达到要求 {p.min_score}"
                )

    # --- 选课 ---

    def select_course(self, student: Student, teaching_class_id: int) -> CourseSelection:
        """学生选课。

        整个方法是一个事务：任一校验失败或写入失败都整体回滚，
        不会出现「计数加了但没有选课记录」的半成功状态。
        """
        # 行级锁：并发选课时序列化到同一教学班，防止超卖（CLAUDE.md §20）
        tc = self.db.execute(
            select(TeachingClass)
            .where(TeachingClass.id == teaching_class_id)
            .options(
                selectinload(TeachingClass.course),
                selectinload(TeachingClass.term),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={teaching_class_id}）")

        if tc.status != "ACTIVE":
            raise Conflict("该教学班已取消")
        if tc.selection_status != "OPEN":
            raise Conflict("该教学班未开放选课")

        # 课程类型校验：必修课只能由教务处预排，学生不能自主选择（TASK-009）
        if not _is_elective(tc.course.course_type if tc.course else None):
            raise Conflict("该课程为必修课，不能自主选择")

        # 统一学期 + 选课窗口 + 限定年级校验（FIX-003）
        self._check_selection_window(student, tc.semester)

        # 重复选课
        existing = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student.id,
                CourseSelection.teaching_class_id == tc.id,
            )
        ).scalar_one_or_none()
        if existing and existing.status == SelectionState.SELECTED:
            raise Conflict("已选过该教学班，不能重复选课")

        # 同一门课的其他教学班
        same_course = self.db.execute(
            select(CourseSelection).where(
                CourseSelection.student_id == student.id,
                CourseSelection.course_id == tc.course_id,
                CourseSelection.semester == tc.semester,
                CourseSelection.status == SelectionState.SELECTED,
                CourseSelection.teaching_class_id != tc.id,
            )
        ).scalars().first()
        if same_course:
            raise Conflict("本学期已选过该课程的其他教学班")

        # 容量（TASK-013）：锁定教学班行后，按 CourseSelection 动态统计已选人数。
        # 必须用锁定读（当前读）：REPEATABLE READ 下普通 COUNT 会读到事务建立时的
        # 旧快照（调用方先加载了 Student），无法看到其他事务刚提交的选课记录。
        enrolled_rows = self.db.execute(
            select(CourseSelection.id)
            .where(
                CourseSelection.teaching_class_id == tc.id,
                CourseSelection.status == SelectionState.SELECTED,
            )
            .with_for_update()
        ).scalars().all()
        enrolled = len(enrolled_rows)
        if enrolled >= tc.capacity:
            raise TeachingClassFull(f"该教学班已满（{enrolled}/{tc.capacity}）")

        # 时间冲突
        hit = ConflictChecker(self.db).student_conflict(student.id, tc.id, tc.semester)
        if hit:
            other = self.db.get(TeachingClass, hit.teaching_class_id)
            raise Conflict(
                f"时间冲突：与 {other.code if other else '已选课程'} "
                f"（周{hit.day_of_week} 第{hit.start_period}-{hit.end_period}节）冲突"
            )

        # 先修课程
        self._check_prerequisites(student.id, tc.course_id)

        try:
            if existing:  # 曾退课，复用该行
                existing.status = SelectionState.SELECTED
                existing.selected_at = datetime.now()
                existing.dropped_at = None
                existing.source = SelectionSource.STUDENT
                sel = existing
            else:
                sel = CourseSelection(
                    student_id=student.id,
                    teaching_class_id=tc.id,
                    course_id=tc.course_id,
                    semester=tc.semester,
                    source=SelectionSource.STUDENT,
                )
                self.db.add(sel)
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            # 唯一约束兜底：并发下两个请求同时通过了应用层检查
            raise Conflict("选课失败：可能已被重复提交") from e
        return sel

    def drop_course(self, student: Student, selection_id: int) -> None:
        sel = self.db.get(CourseSelection, selection_id)
        if sel is None:
            raise NotFound("选课记录不存在")
        if sel.student_id != student.id:
            raise PermissionDenied("只能退选本人的课程")
        if sel.status != SelectionState.SELECTED:
            raise Conflict("该记录已退课")

        # 必修课不能通过学生自主退选接口删除，调整由教务处负责（TASK-009）
        if not _is_elective(sel.course.course_type if sel.course else None):
            raise Conflict("必修课不能由学生自主退选")

        tc = self.db.execute(
            select(TeachingClass)
            .where(TeachingClass.id == sel.teaching_class_id)
            .options(selectinload(TeachingClass.term))
            .with_for_update()
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound("教学班不存在")
        if tc.status != "ACTIVE":
            raise Conflict("该教学班已取消，无法退课")
        if tc.selection_status != "OPEN":
            raise Conflict("该教学班未开放选课，无法退课")

        # 学期 + 选课窗口 + 限定年级统一校验（FIX-003）
        self._check_selection_window(student, tc.semester)

        # 已有成绩不允许退课
        g = self.db.execute(
            select(Grade).where(
                Grade.student_id == student.id,
                Grade.teaching_class_id == sel.teaching_class_id,
            )
        ).scalars().first()
        if g and g.status != GradeStatus.DRAFT:
            raise Conflict("该课程已有成绩记录，无法退课")

        sel.status = SelectionState.DROPPED
        sel.dropped_at = datetime.now()
        self.db.commit()

    # --- 必修课预排 ---

    def _validate_arrangement_class(
        self, teaching_class_id: int, *, lock: bool
    ) -> TeachingClass:
        """校验教学班可用于必修课预安排，并返回带 course/term 的对象。"""
        stmt = (
            select(TeachingClass)
            .where(TeachingClass.id == teaching_class_id)
            .options(
                selectinload(TeachingClass.course),
                selectinload(TeachingClass.term),
                selectinload(TeachingClass.schedules),
            )
        )
        if lock:
            stmt = stmt.with_for_update()
        tc = self.db.execute(stmt).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={teaching_class_id}）")
        if tc.status != "ACTIVE":
            raise Conflict("该教学班已取消，无法安排学生")
        if tc.course is None:
            raise NotFound("教学班关联课程不存在")
        if not _is_required(tc.course.course_type):
            raise Conflict("该课程不是必修/实践课程，不能使用必修课预安排")
        if tc.term is None or tc.term.status != TermStatus.ACTIVE:
            raise Conflict("当前学期未在进行中，无法安排必修课")
        if tc.teacher_id is None:
            raise Conflict("尚未分配授课教师，无法安排学生")
        if not tc.schedules:
            raise Conflict("尚未安排上课时间，无法安排学生")
        return tc

    def _scope_students(
        self,
        college_id: int | None,
        major_id: int | None,
        class_id: int | None,
    ) -> tuple[list[Student], dict[str, int]]:
        """按行政班 > 专业 > 学院的范围返回学生及范围描述。"""
        if class_id is not None:
            if self.db.get(Class, class_id) is None:
                raise NotFound(f"行政班不存在（id={class_id}）")
            cond = Student.class_id == class_id
            scope = {"class_id": class_id}
        elif major_id is not None:
            if self.db.get(Major, major_id) is None:
                raise NotFound(f"专业不存在（id={major_id}）")
            cond = Student.major_id == major_id
            scope = {"major_id": major_id}
        elif college_id is not None:
            if self.db.get(College, college_id) is None:
                raise NotFound(f"学院不存在（id={college_id}）")
            cond = Student.college_id == college_id
            scope = {"college_id": college_id}
        else:
            raise Conflict("必须指定预排范围：行政班、专业或学院")

        students = list(
            self.db.execute(
                select(Student)
                .options(
                    selectinload(Student.user),
                    selectinload(Student.klass),
                    selectinload(Student.major),
                )
                .where(cond)
                .order_by(Student.student_no)
            ).scalars()
        )
        return students, scope

    def _selected_count(self, teaching_class_id: int, *, lock: bool) -> int:
        stmt = select(CourseSelection.id).where(
            CourseSelection.teaching_class_id == teaching_class_id,
            CourseSelection.status == SelectionState.SELECTED,
        )
        if lock:
            stmt = stmt.with_for_update()
        return len(self.db.execute(stmt).scalars().all())

    def _existing_rows(
        self,
        student_ids: list[int],
        tc: TeachingClass,
        *,
        lock: bool,
    ) -> list[CourseSelection]:
        if not student_ids:
            return []
        stmt = select(CourseSelection).where(
            CourseSelection.student_id.in_(student_ids),
            CourseSelection.semester == tc.semester,
            or_(
                CourseSelection.teaching_class_id == tc.id,
                CourseSelection.course_id == tc.course_id,
            ),
        )
        if lock:
            stmt = stmt.with_for_update()
        return list(self.db.execute(stmt).scalars())

    def _plan_arrangement(
        self,
        tc: TeachingClass,
        students: list[Student],
        existing_rows: list[CourseSelection],
        selected_count: int,
        *,
        preview: bool,
    ) -> dict:
        """计算预安排结果；preview=True 时不做任何写入。

        原子性策略：应用层支持“部分成功 + 逐条原因”，但所有新增记录
        仍在同一个数据库事务中提交；提交失败则整批回滚。
        """
        same_class: dict[int, CourseSelection] = {}
        same_course_other: dict[int, CourseSelection] = {}
        for row in existing_rows:
            if row.teaching_class_id == tc.id:
                same_class[row.student_id] = row
            elif (
                row.status == SelectionState.SELECTED
                and row.course_id == tc.course_id
            ):
                same_course_other[row.student_id] = row

        remaining = max(0, tc.capacity - selected_count)
        items: list[dict] = []
        reason_counts: dict[str, int] = {}
        already = would_add = skipped = 0
        conflict_count = ineligible_count = 0
        checker = ConflictChecker(self.db)

        for stu in students:
            item = {
                "student_id": stu.id,
                "student_no": stu.student_no,
                "student_name": stu.user.real_name if stu.user else "",
                "class_name": stu.klass.name if stu.klass else None,
                "major_name": stu.major.name if stu.major else None,
                "action": "ADD",
                "reason_code": None,
                "reason": None,
            }
            same = same_class.get(stu.id)
            if same is not None and same.status == SelectionState.SELECTED:
                item.update(
                    action="ALREADY",
                    reason_code="ALREADY_ASSIGNED",
                    reason="已在本教学班",
                )
                already += 1
            elif same is not None and same.status == SelectionState.DROPPED:
                item.update(
                    action="SKIP",
                    reason_code="PREVIOUSLY_REMOVED",
                    reason="曾从本教学班移除，批量预排不自动恢复",
                )
                skipped += 1
                ineligible_count += 1
            elif stu.academic_status != "ENROLLED":
                item.update(
                    action="SKIP",
                    reason_code="INVALID_STATUS",
                    reason=f"学籍状态为 {stu.academic_status}",
                )
                skipped += 1
                ineligible_count += 1
            elif stu.id in same_course_other:
                item.update(
                    action="SKIP",
                    reason_code="SAME_COURSE_OTHER_CLASS",
                    reason="已选同课程其他教学班",
                )
                skipped += 1
                ineligible_count += 1
            else:
                hit = checker.student_conflict(stu.id, tc.id, tc.semester)
                if hit is not None:
                    other = self.db.get(TeachingClass, hit.teaching_class_id)
                    item.update(
                        action="SKIP",
                        reason_code="TIME_CONFLICT",
                        reason=f"与 {other.code if other else '已选课程'} 时间冲突",
                    )
                    skipped += 1
                    conflict_count += 1
                elif would_add >= remaining:
                    item.update(
                        action="SKIP",
                        reason_code="CAPACITY_FULL",
                        reason=f"教学班剩余容量不足（剩余 {remaining}）",
                    )
                    skipped += 1
                else:
                    would_add += 1

            if item["reason_code"]:
                code = item["reason_code"]
                reason_counts[code] = reason_counts.get(code, 0) + 1
            items.append(item)

        selected_after = selected_count + would_add
        return {
            "teaching_class_id": tc.id,
            "teaching_class_code": tc.code,
            "course_code": tc.course.code if tc.course else None,
            "course_name": tc.course.name if tc.course else None,
            "scope": {},  # 由 assign_required 填入
            "matched": len(students),
            "already_assigned": already,
            "would_add": would_add,
            "added": 0,
            "skipped": skipped,
            "capacity": tc.capacity,
            "selected_count": selected_count,
            "selected_count_after": selected_after,
            "remaining": remaining,
            "remaining_after": max(0, tc.capacity - selected_after),
            "conflict_count": conflict_count,
            "ineligible_count": ineligible_count,
            "reason_counts": reason_counts,
            "preview": preview,
            "committed": False,
            "items": items,
        }

    def _log_operation(
        self,
        operator: User | None,
        *,
        action: str,
        resource_type: str,
        resource_id: int,
        detail: str,
    ) -> None:
        self.db.add(
            OperationLog(
                user_id=operator.id if operator else None,
                username=operator.username if operator else None,
                action=action,
                module="selection",
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail[:500],
                result="SUCCESS",
            )
        )

    @staticmethod
    def _assign_detail(tc: TeachingClass, scope: dict[str, int], result: dict) -> str:
        scope_text = ", ".join(f"{k}={v}" for k, v in scope.items())
        reason_text = ", ".join(
            f"{REASON_LABELS.get(k, k)} {v}"
            for k, v in result["reason_counts"].items()
        ) or "无"
        return (
            f"必修课预安排：教学班 {tc.code}，范围 {scope_text}，"
            f"匹配 {result['matched']} 人，已安排 {result['already_assigned']} 人，"
            f"新增 {result['added']} 人，跳过 {result['skipped']} 人；原因：{reason_text}"
        )

    def _commit(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            conflict = conflict_from_integrity_error(exc, "选课记录")
            if conflict is not None:
                raise conflict from exc
            raise

    def assign_required(
        self,
        teaching_class_id: int,
        college_id: int | None = None,
        major_id: int | None = None,
        class_id: int | None = None,
        *,
        preview: bool = False,
        operator: User | None = None,
    ) -> dict:
        """必修课预安排：按行政班/专业/学院批量安排学生。

        - ``preview=True``：只计算并返回预览，不写库；
        - ``preview=False``：在一个事务内写入所有可新增记录；
          应用层跳过不符合条件的学生，逐条返回原因；提交失败整批回滚。
        - 重复执行幂等：已在本班的学生返回 ALREADY，不重复创建。
        - 曾被移除（DROPPED）的学生不自动恢复，需教务手动添加。
        """
        tc = self._validate_arrangement_class(teaching_class_id, lock=not preview)
        students, scope = self._scope_students(
            college_id=college_id, major_id=major_id, class_id=class_id
        )
        student_ids = [s.id for s in students]

        if preview:
            selected_count = self._selected_count(tc.id, lock=False)
            existing = self._existing_rows(student_ids, tc, lock=False)
            result = self._plan_arrangement(
                tc, students, existing, selected_count, preview=True
            )
            result["scope"] = scope
            return result

        selected_count = self._selected_count(tc.id, lock=True)
        existing = self._existing_rows(student_ids, tc, lock=True)
        result = self._plan_arrangement(
            tc, students, existing, selected_count, preview=False
        )
        result["scope"] = scope

        now = datetime.now()
        add_ids = [i["student_id"] for i in result["items"] if i["action"] == "ADD"]
        try:
            for sid in add_ids:
                self.db.add(
                    CourseSelection(
                        student_id=sid,
                        teaching_class_id=tc.id,
                        course_id=tc.course_id,
                        semester=tc.semester,
                        status=SelectionState.SELECTED,
                        source=SelectionSource.ADMIN_REQUIRED,
                        selected_at=now,
                    )
                )
            result["added"] = len(add_ids)
            result["selected_count_after"] = selected_count + len(add_ids)
            result["remaining_after"] = max(
                0, tc.capacity - result["selected_count_after"]
            )
            self._log_operation(
                operator,
                action="REQUIRED_ASSIGN",
                resource_type="teaching_class",
                resource_id=tc.id,
                detail=self._assign_detail(tc, scope, result),
            )
            self._commit()
            result["committed"] = True
        except Exception:
            self.db.rollback()
            raise
        return result

    # --- 可选课程 ---

    def available_classes(
        self, student: Student, semester: str, keyword: str | None = None
    ) -> list[TeachingClass]:
        """学生可选的教学班列表（仅选修课，且未选过，同课程其他教学班也排除）。"""
        selected = list(
            self.db.execute(
                select(CourseSelection).where(
                    CourseSelection.student_id == student.id,
                    CourseSelection.semester == semester,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        selected_tc_ids = {s.teaching_class_id for s in selected}
        selected_course_ids = {s.course_id for s in selected}

        stmt = (
            select(TeachingClass)
            .options(
                selectinload(TeachingClass.course),
                selectinload(TeachingClass.teacher).selectinload(Teacher.user),
                selectinload(TeachingClass.schedules).selectinload(Schedule.classroom),
            )
            .where(
                TeachingClass.semester == semester,
                TeachingClass.selection_status == "OPEN",
                TeachingClass.status == "ACTIVE",
                TeachingClass.course.has(Course.course_type.in_(_ELECTIVE_TYPES)),
            )
        )
        if selected_tc_ids:
            stmt = stmt.where(TeachingClass.id.not_in(selected_tc_ids))
        if selected_course_ids:
            stmt = stmt.where(TeachingClass.course_id.not_in(selected_course_ids))
        rows = list(self.db.execute(stmt).scalars())
        if keyword:
            k = keyword.lower()
            rows = [
                r
                for r in rows
                if r.course and (k in r.course.name.lower() or k in r.course.code.lower())
            ]
        return rows

    def stats_by_class(self, teaching_class_id: int) -> dict:
        total = (
            self.db.execute(
                select(func.count())
                .select_from(CourseSelection)
                .where(
                    CourseSelection.teaching_class_id == teaching_class_id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalar()
            or 0
        )
        tc = self.db.get(TeachingClass, teaching_class_id)
        return {
            "teaching_class_id": teaching_class_id,
            "selected": total,
            "capacity": tc.capacity if tc else 0,
            "remaining": max(0, (tc.capacity - total)) if tc else 0,
        }
