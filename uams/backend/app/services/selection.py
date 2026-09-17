"""选课业务逻辑。

这是全系统并发要求最高的模块（CLAUDE.md §19/§20）：
  - 选课必须在单个事务内完成「校验 → 建记录 → 更新计数」
  - 必须用 SELECT ... FOR UPDATE 锁住教学班行，防止超卖
  - 唯一约束 uk_selection 作为最后一道防线
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.models.course import Course, CoursePrerequisite, CourseType
from app.models.grade import Grade, GradeStatus
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionPeriod, SelectionState
from app.models.teaching import Schedule, TeachingClass
from app.services.teaching import ConflictChecker

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

    def _check_period_open(self, student: Student, semester: str) -> None:
        periods = list(
            self.db.execute(
                select(SelectionPeriod).where(SelectionPeriod.semester == semester)
            ).scalars()
        )
        if not periods:
            raise Conflict("本学期尚未设置选课时间，无法选课")
        if not any(p.is_open_now(student.enrollment_year) for p in periods):
            raise Conflict("当前不在选课时间内")

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
            .options(selectinload(TeachingClass.course))
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

        self._check_period_open(student, tc.semester)

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

        # 容量（此处读到的是加锁后的值）
        if tc.selected_count >= tc.capacity:
            raise Conflict(f"该教学班已满（{tc.selected_count}/{tc.capacity}）")

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
                sel = existing
            else:
                sel = CourseSelection(
                    student_id=student.id,
                    teaching_class_id=tc.id,
                    course_id=tc.course_id,
                    semester=tc.semester,
                )
                self.db.add(sel)
            tc.selected_count += 1
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
            .with_for_update()
        ).scalar_one_or_none()
        if tc and tc.selection_status != "OPEN":
            raise Conflict("当前不在选课时间内，无法退课")

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
        if tc:
            tc.selected_count = max(0, tc.selected_count - 1)
        self.db.commit()

    # --- 必修课预排 ---

    def assign_required(
        self,
        teaching_class_id: int,
        college_id: int | None = None,
        major_id: int | None = None,
        class_id: int | None = None,
    ) -> dict:
        """必修课预安排：教务处按范围（行政班 > 专业 > 学院）把学生安排进教学班。

        范围优先级：class_id > major_id > college_id。
        幂等：同一学生同一教学班已有记录时不重复创建，曾退课则复用该行。
        """
        tc = self.db.execute(
            select(TeachingClass)
            .where(TeachingClass.id == teaching_class_id)
            .options(selectinload(TeachingClass.course))
        ).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"教学班不存在（id={teaching_class_id}）")

        # 只允许必修课通过预排接口安排（TASK-009）
        if not _is_required(tc.course.course_type if tc.course else None):
            raise Conflict("该课程为选修课，不能通过必修课预排接口安排")

        if class_id is None and major_id is None and college_id is None:
            raise Conflict("必须指定预排范围：行政班、专业或学院")

        if class_id is not None:
            cond = (Student.class_id == class_id,)
            scope = {"class_id": class_id}
        elif major_id is not None:
            cond = (Student.major_id == major_id,)
            scope = {"major_id": major_id}
        else:
            cond = (Student.college_id == college_id,)
            scope = {"college_id": college_id}

        student_ids = [
            row[0] for row in self.db.execute(select(Student.id).where(*cond)).all()
        ]

        assigned = 0
        skipped = 0
        for sid in student_ids:
            sel = self.db.execute(
                select(CourseSelection).where(
                    CourseSelection.student_id == sid,
                    CourseSelection.teaching_class_id == tc.id,
                )
            ).scalar_one_or_none()
            if sel is not None and sel.status == SelectionState.SELECTED:
                skipped += 1
                continue
            if sel is not None:  # 曾退课，复用该行
                sel.status = SelectionState.SELECTED
                sel.selected_at = datetime.now()
                sel.dropped_at = None
            else:
                sel = CourseSelection(
                    student_id=sid,
                    teaching_class_id=tc.id,
                    course_id=tc.course_id,
                    semester=tc.semester,
                )
                self.db.add(sel)
            assigned += 1
        tc.selected_count += assigned
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise Conflict("预排失败：存在重复选课记录") from e
        return {
            "teaching_class_id": tc.id,
            "scope": scope,
            "matched": len(student_ids),
            "assigned": assigned,
            "skipped": skipped,
        }

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
            "counter_consistent": (tc.selected_count == total) if tc else False,
        }
