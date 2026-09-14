"""成绩业务逻辑。

状态机（DATABASE.md §9.2）：
    DRAFT --提交--> SUBMITTED --通过--> APPROVED（对学生可见）
                        └--驳回--> REJECTED --修改--> SUBMITTED

规则（CLAUDE.md §18）：
  - APPROVED 后普通教师不可直接修改
  - 学生只能查询 APPROVED 的成绩
  - 总评由后端按课程权重统一计算，不接受前端传入
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass


class GradeService:
    def __init__(self, db: Session):
        self.db = db

    def base_stmt(self) -> Select:
        return select(Grade).options(
            selectinload(Grade.course),
            selectinload(Grade.student).selectinload(Student.user),
            selectinload(Grade.teaching_class),
        )

    def get_or_404(self, grade_id: int) -> Grade:
        g = self.db.get(Grade, grade_id)
        if g is None:
            raise NotFound(f"成绩记录不存在（id={grade_id}）")
        return g

    # --- 教师侧 ---

    def ensure_teacher_owns(self, teacher: Teacher, teaching_class_id: int) -> TeachingClass:
        tc = self.db.get(TeachingClass, teaching_class_id)
        if tc is None:
            raise NotFound("教学班不存在")
        if tc.teacher_id != teacher.id:
            raise PermissionDenied("只能操作本人授课教学班的成绩")
        return tc

    def init_sheet(self, teaching_class_id: int) -> list[Grade]:
        """为教学班已选学生生成成绩草稿行（幂等）。"""
        tc = self.db.get(TeachingClass, teaching_class_id)
        if tc is None:
            raise NotFound("教学班不存在")
        course = self.db.get(Course, tc.course_id)

        selections = list(
            self.db.execute(
                select(CourseSelection).where(
                    CourseSelection.teaching_class_id == teaching_class_id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        existing = {
            g.student_id
            for g in self.db.execute(
                select(Grade).where(Grade.teaching_class_id == teaching_class_id)
            ).scalars()
        }
        created = 0
        for s in selections:
            if s.student_id in existing:
                continue
            self.db.add(
                Grade(
                    student_id=s.student_id,
                    teaching_class_id=teaching_class_id,
                    course_id=tc.course_id,
                    semester=tc.semester,
                    # 学分快照：课程学分日后调整不影响历史成绩
                    credits=course.credits if course else Decimal("0"),
                )
            )
            created += 1
        self.db.commit()
        return self.list_by_class(teaching_class_id)

    def list_by_class(self, teaching_class_id: int) -> list[Grade]:
        return list(
            self.db.execute(
                self.base_stmt()
                .where(Grade.teaching_class_id == teaching_class_id)
                .order_by(Grade.student_id)
            ).scalars()
        )

    def save_scores(
        self, teacher: Teacher, teaching_class_id: int, items: list[dict]
    ) -> list[Grade]:
        """批量录入成绩。整批在一个事务内提交。"""
        tc = self.ensure_teacher_owns(teacher, teaching_class_id)
        course = self.db.get(Course, tc.course_id)
        if course is None:
            raise NotFound("课程不存在")

        by_id = {
            g.id: g
            for g in self.db.execute(
                select(Grade).where(Grade.teaching_class_id == teaching_class_id)
            ).scalars()
        }
        for item in items:
            g = by_id.get(item["grade_id"])
            if g is None:
                raise NotFound(f"成绩记录不存在（id={item['grade_id']}）")
            if g.status == GradeStatus.APPROVED:
                raise Conflict("成绩已审核通过，教师不可直接修改")
            if g.status == GradeStatus.SUBMITTED:
                raise Conflict("成绩已提交待审核，请先由教务驳回后再修改")
            if "regular_score" in item:
                g.regular_score = item["regular_score"]
            if "final_score" in item:
                g.final_score = item["final_score"]
            # 总评由后端算，忽略前端可能传来的 total_score
            g.compute(course.regular_weight, course.final_weight)
            g.status = GradeStatus.DRAFT
        self.db.commit()
        return self.list_by_class(teaching_class_id)

    def submit(self, teacher: Teacher, teaching_class_id: int) -> int:
        """提交整个教学班的成绩。"""
        self.ensure_teacher_owns(teacher, teaching_class_id)
        rows = list(
            self.db.execute(
                select(Grade).where(
                    Grade.teaching_class_id == teaching_class_id,
                    Grade.status.in_([GradeStatus.DRAFT, GradeStatus.REJECTED]),
                )
            ).scalars()
        )
        if not rows:
            raise Conflict("没有可提交的成绩（草稿或已驳回状态）")
        incomplete = [r for r in rows if r.total_score is None]
        if incomplete:
            raise Conflict(f"还有 {len(incomplete)} 名学生成绩未录入完整，无法提交")

        now = datetime.now()
        for r in rows:
            r.status = GradeStatus.SUBMITTED
            r.submitted_by = teacher.id
            r.submitted_at = now
            r.reject_reason = None
        self.db.commit()
        return len(rows)

    # --- 教务侧 ---

    def approve(self, approver_id: int, grade_ids: list[int]) -> int:
        rows = list(
            self.db.execute(select(Grade).where(Grade.id.in_(grade_ids))).scalars()
        )
        if not rows:
            raise NotFound("未找到成绩记录")
        bad = [r.id for r in rows if r.status != GradeStatus.SUBMITTED]
        if bad:
            raise Conflict(f"只有已提交的成绩可以审核，问题记录：{bad[:5]}")

        now = datetime.now()
        for r in rows:
            r.status = GradeStatus.APPROVED
            r.approved_by = approver_id
            r.approved_at = now
        self.db.commit()
        self._refresh_student_credits({r.student_id for r in rows})
        return len(rows)

    def reject(self, approver_id: int, grade_ids: list[int], reason: str) -> int:
        rows = list(
            self.db.execute(select(Grade).where(Grade.id.in_(grade_ids))).scalars()
        )
        if not rows:
            raise NotFound("未找到成绩记录")
        bad = [r.id for r in rows if r.status != GradeStatus.SUBMITTED]
        if bad:
            raise Conflict(f"只有已提交的成绩可以驳回，问题记录：{bad[:5]}")
        for r in rows:
            r.status = GradeStatus.REJECTED
            r.approved_by = approver_id
            r.approved_at = datetime.now()
            r.reject_reason = reason
        self.db.commit()
        return len(rows)

    def _refresh_student_credits(self, student_ids: set[int]) -> None:
        """重算已修学分与 GPA（仅统计已审核且及格的成绩）。"""
        for sid in student_ids:
            rows = list(
                self.db.execute(
                    select(Grade).where(
                        Grade.student_id == sid,
                        Grade.status == GradeStatus.APPROVED,
                    )
                ).scalars()
            )
            passed = [r for r in rows if r.is_passed]
            total_credits = sum((Decimal(str(r.credits)) for r in passed), Decimal("0"))
            weighted = sum(
                (
                    Decimal(str(r.credits)) * Decimal(str(r.grade_point or 0))
                    for r in passed
                ),
                Decimal("0"),
            )
            stu = self.db.get(Student, sid)
            if stu:
                stu.total_credits = total_credits
                stu.gpa = (
                    (weighted / total_credits).quantize(Decimal("0.01"))
                    if total_credits
                    else None
                )
        self.db.commit()

    # --- 学生侧 ---

    def list_by_student(self, student_id: int, semester: str | None = None) -> list[Grade]:
        """学生只能看到已审核通过的成绩（CLAUDE.md §18）。"""
        stmt = self.base_stmt().where(
            Grade.student_id == student_id, Grade.status == GradeStatus.APPROVED
        )
        if semester:
            stmt = stmt.where(Grade.semester == semester)
        return list(self.db.execute(stmt.order_by(Grade.semester.desc())).scalars())

    def pending_approval(self, semester: str | None = None) -> list[Grade]:
        stmt = self.base_stmt().where(Grade.status == GradeStatus.SUBMITTED)
        if semester:
            stmt = stmt.where(Grade.semester == semester)
        return list(self.db.execute(stmt).scalars())

    def student_summary(self, student_id: int) -> dict:
        rows = self.list_by_student(student_id)
        passed = [r for r in rows if r.is_passed]
        total = sum((Decimal(str(r.credits)) for r in passed), Decimal("0"))
        weighted = sum(
            (Decimal(str(r.credits)) * Decimal(str(r.grade_point or 0)) for r in passed),
            Decimal("0"),
        )
        return {
            "total_courses": len(rows),
            "passed_courses": len(passed),
            "failed_courses": len(rows) - len(passed),
            "total_credits": float(total),
            "gpa": float((weighted / total).quantize(Decimal("0.01"))) if total else None,
        }

    def class_statistics(self, teaching_class_id: int) -> dict:
        rows = [
            g
            for g in self.list_by_class(teaching_class_id)
            if g.total_score is not None
        ]
        if not rows:
            return {"count": 0}
        scores = [float(g.total_score) for g in rows]
        buckets = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
        for s in scores:
            if s >= 90: buckets["90-100"] += 1
            elif s >= 80: buckets["80-89"] += 1
            elif s >= 70: buckets["70-79"] += 1
            elif s >= 60: buckets["60-69"] += 1
            else: buckets["<60"] += 1
        return {
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 2),
            "max": max(scores),
            "min": min(scores),
            "pass_rate": round(len([s for s in scores if s >= 60]) / len(scores) * 100, 2),
            "distribution": buckets,
        }
