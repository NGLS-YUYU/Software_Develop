"""成绩业务逻辑。

状态机（DATABASE.md §9.2）：
    DRAFT --提交--> SUBMITTED --通过--> APPROVED（对学生可见）
                        └--驳回--> REJECTED --修改--> SUBMITTED

规则（CLAUDE.md §18）：
  - APPROVED 后普通教师不可直接修改
  - 学生只能查询 APPROVED 的成绩
  - 总评由后端按课程权重统一计算，不接受前端传入
"""

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.models.course import Course
from app.models.grade import Grade, GradeChangeLog, GradeStatus
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.services.assessment import profile_for
from app.services.gpa_service import GpaError, GpaService, NoGradesError
from app.services.ranking_service import RankingService
from app.services.score_service import ScoreService


class GradeService:
    def __init__(self, db: Session):
        self.db = db

    def base_stmt(self) -> Select:
        return select(Grade).options(
            selectinload(Grade.course),
            selectinload(Grade.student).selectinload(Student.user),
            selectinload(Grade.teaching_class)
            .selectinload(TeachingClass.teacher)
            .selectinload(Teacher.user),
        )

    def get_or_404(self, grade_id: int) -> Grade:
        g = self.db.get(Grade, grade_id)
        if g is None:
            raise NotFound(f"成绩记录不存在（id={grade_id}）")
        return g

    _SCORE_FIELDS = (
        "regular_score", "mid_score", "mid_theory_score", "mid_practice_score",
        "final_score", "final_theory_score", "final_practice_score",
        "theory_makeup_score", "practice_makeup_score",
    )

    @staticmethod
    def _snapshot(g: Grade) -> dict:
        return {
            "id": g.id,
            "student_id": g.student_id,
            "teaching_class_id": g.teaching_class_id,
            "course_id": g.course_id,
            "semester": g.semester,
            **{f: getattr(g, f) for f in GradeService._SCORE_FIELDS},
            "theory_total_score": g.theory_total_score,
            "practice_total_score": g.practice_total_score,
            "total_score": g.total_score,
            "grade_point": g.grade_point,
            "credits": g.credits,
            "is_passed": g.is_passed,
            "status": g.status,
            "submitted_by": g.submitted_by,
            "submitted_at": g.submitted_at,
            "approved_by": g.approved_by,
            "approved_at": g.approved_at,
            "reject_reason": g.reject_reason,
        }

    def _log_change(
        self,
        g: Grade,
        action: str,
        reason: str,
        operator_id: int | None,
        before: dict,
        after: dict,
    ) -> None:
        self.db.add(
            GradeChangeLog(
                grade_id=g.id,
                student_id=g.student_id,
                teaching_class_id=g.teaching_class_id,
                course_id=g.course_id,
                action=action,
                reason=reason[:500],
                before_snapshot=json.dumps(before, ensure_ascii=False, default=str),
                after_snapshot=json.dumps(after, ensure_ascii=False, default=str),
                operated_by=operator_id,
            )
        )

    def history(self, grade_id: int) -> list[GradeChangeLog]:
        self.get_or_404(grade_id)
        return list(
            self.db.execute(
                select(GradeChangeLog)
                .where(GradeChangeLog.grade_id == grade_id)
                .order_by(GradeChangeLog.operated_at.desc(), GradeChangeLog.id.desc())
            ).scalars()
        )

    def list_approved(self, semester: str | None = None) -> list[Grade]:
        stmt = self.base_stmt().where(Grade.status == GradeStatus.APPROVED)
        if semester:
            stmt = stmt.where(Grade.semester == semester)
        return list(self.db.execute(stmt.order_by(Grade.semester.desc(), Grade.id)).scalars())

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

    @staticmethod
    def _entry_status(g: Grade | None) -> str:
        """成绩录入状态：未录入（无成绩或全部为空）/草稿/待审核/已通过/已驳回。"""
        if g is None:
            return "NOT_ENTERED"
        scores = (
            g.regular_score, g.mid_score, g.mid_theory_score, g.mid_practice_score,
            g.final_score, g.final_theory_score, g.final_practice_score,
            g.theory_makeup_score, g.practice_makeup_score,
        )
        if all(v is None for v in scores):
            return "NOT_ENTERED"
        return g.status

    def roster(self, teaching_class_id: int) -> list[dict]:
        """教学班学生名单 + 成绩录入状态（TASK-005）。"""
        if self.db.get(TeachingClass, teaching_class_id) is None:
            raise NotFound("教学班不存在")
        selections = list(
            self.db.execute(
                select(CourseSelection).where(
                    CourseSelection.teaching_class_id == teaching_class_id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        grades = {
            g.student_id: g
            for g in self.db.execute(
                select(Grade).where(Grade.teaching_class_id == teaching_class_id)
            ).scalars()
        }
        out: list[dict] = []
        for s in selections:
            stu = s.student
            if stu is None:
                continue
            g = grades.get(s.student_id)
            out.append(
                {
                    "student_id": stu.id,
                    "student_no": stu.student_no,
                    "student_name": stu.user.real_name if stu.user else "",
                    "grade_id": g.id if g else None,
                    "entry_status": self._entry_status(g),
                }
            )
        out.sort(key=lambda r: r["student_no"])
        return out

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
            before = self._snapshot(g) if g.status == GradeStatus.REJECTED else None
            if "regular_score" in item:
                g.regular_score = item["regular_score"]
            if "mid_score" in item:
                g.mid_score = item["mid_score"]
            if "mid_theory_score" in item:
                g.mid_theory_score = item["mid_theory_score"]
            if "mid_practice_score" in item:
                g.mid_practice_score = item["mid_practice_score"]
            if "final_score" in item:
                g.final_score = item["final_score"]
            if "final_theory_score" in item:
                g.final_theory_score = item["final_theory_score"]
            if "final_practice_score" in item:
                g.final_practice_score = item["final_practice_score"]
            if "theory_makeup_score" in item:
                g.theory_makeup_score = item["theory_makeup_score"]
            if "practice_makeup_score" in item:
                g.practice_makeup_score = item["practice_makeup_score"]
            # 总评由统一成绩计算服务计算（TASK-003）；忽略前端可能传来的 total_score。
            # 草稿保存允许成绩不完整：此时总评置空，提交时再拦截。
            ScoreService.compute_for_draft(course, g)
            g.status = GradeStatus.DRAFT
            if before is not None:
                self._log_change(
                    g, "TEACHER_EDIT", "教师修改已驳回成绩",
                    teacher.user_id, before, self._snapshot(g),
                )
        self.db.commit()
        return self.list_by_class(teaching_class_id)

    def delete_draft(self, teacher: Teacher | None, grade_id: int) -> None:
        """删除成绩草稿（FIX-005 §十二/§十三/§十五）。

        状态约束：**只有 DRAFT 允许删除**。SUBMITTED / APPROVED / REJECTED 一律拒绝
        （409），因为这几类记录已经进入提交/审核链路，删除会破坏成绩留痕；
        前端隐藏按钮不算数，这里必须做后端校验。

        草稿与正式成绩共用 ``grades`` 表，因此删除严格依赖 ``status == DRAFT``，
        绝不按 id 直接删。
        """
        g = self.get_or_404(grade_id)
        if teacher is not None and g.teaching_class is not None:
            if g.teaching_class.teacher_id != teacher.id:
                raise PermissionDenied("只能删除本人授课教学班的成绩草稿")
        if g.status != GradeStatus.DRAFT:
            raise Conflict(
                f"只有草稿可以删除，当前状态为 {g.status}，请先由教务驳回后再处理"
            )
        self.db.delete(g)
        self.db.commit()

    def import_scores(self, rows: list[dict]) -> int:
        """教务 Excel 批量导入成绩（TASK-010）。

        复用 ScoreService 统一计算，禁止自行计算权重/绩点；一律保存为 DRAFT，
        不写 GPA / 排名。rows 中的每一行已由 ImportService 完成业务校验：
        ``{student_id, teaching_class_id, scores: {field: Decimal}}``。
        """
        for row in rows:
            tc = self.db.get(TeachingClass, row["teaching_class_id"])
            if tc is None:
                raise NotFound("教学班不存在")
            course = self.db.get(Course, tc.course_id)

            g = self.db.execute(
                select(Grade).where(
                    Grade.student_id == row["student_id"],
                    Grade.teaching_class_id == row["teaching_class_id"],
                )
            ).scalar_one_or_none()
            if g is None:
                g = Grade(
                    student_id=row["student_id"],
                    teaching_class_id=tc.id,
                    course_id=tc.course_id,
                    semester=tc.semester,
                    # 学分快照与手工录入一致（DATABASE.md §9.1）
                    credits=course.credits if course else Decimal("0"),
                )
                self.db.add(g)
            elif g.status in (GradeStatus.SUBMITTED, GradeStatus.APPROVED):
                # 防御性校验：正常情况下 ImportService 已拦截
                raise Conflict("成绩已提交或已审核，不能通过导入覆盖")

            for field, value in row["scores"].items():
                setattr(g, field, value)
            # 总评由统一成绩计算服务计算（TASK-003）；草稿允许不完整。
            ScoreService.compute_for_draft(course, g)
            g.status = GradeStatus.DRAFT
        self.db.commit()
        return len(rows)

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
            before = self._snapshot(r)
            r.status = GradeStatus.SUBMITTED
            r.submitted_by = teacher.id
            r.submitted_at = now
            r.reject_reason = None
            self._log_change(
                r, "SUBMIT", "教师提交成绩", teacher.user_id, before, self._snapshot(r)
            )
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
            before = self._snapshot(r)
            r.status = GradeStatus.APPROVED
            r.approved_by = approver_id
            r.approved_at = now
            self._log_change(
                r, "APPROVE", "教务审核通过", approver_id, before, self._snapshot(r)
            )
        # 成绩状态与学分/GPA 必须在同一事务内提交，避免成绩已生效但统计未更新。
        self.db.flush()
        self._refresh_student_credits({r.student_id for r in rows})
        self.db.commit()
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
            before = self._snapshot(r)
            r.status = GradeStatus.REJECTED
            r.approved_by = approver_id
            r.approved_at = datetime.now()
            r.reject_reason = reason
            self._log_change(
                r, "REJECT", reason, approver_id, before, self._snapshot(r)
            )
        self.db.commit()
        return len(rows)

    def unapprove(self, operator_id: int, grade_id: int, reason: str) -> Grade:
        """撤销已审核成绩（F-03），允许教师重新修改并提交。"""
        g = self.db.execute(
            select(Grade).where(Grade.id == grade_id).with_for_update()
        ).scalar_one_or_none()
        if g is None:
            raise NotFound(f"成绩记录不存在（id={grade_id}）")
        if g.status != GradeStatus.APPROVED:
            raise Conflict("只有已审核通过的成绩可以撤销审核")
        before = self._snapshot(g)
        g.status = GradeStatus.REJECTED
        g.reject_reason = reason
        g.approved_by = None
        g.approved_at = None
        self._log_change(
            g, "UN_APPROVE", reason, operator_id, before, self._snapshot(g)
        )
        self.db.flush()
        self._refresh_student_credits({g.student_id})
        self.db.commit()
        return g

    def correct(
        self,
        operator_id: int,
        grade_id: int,
        updates: dict,
        reason: str,
    ) -> Grade:
        """教务直接更正已审核成绩（F-03），保留完整前后快照。"""
        g = self.db.execute(
            select(Grade).where(Grade.id == grade_id).with_for_update()
        ).scalar_one_or_none()
        if g is None:
            raise NotFound(f"成绩记录不存在（id={grade_id}）")
        if g.status != GradeStatus.APPROVED:
            raise Conflict("只有已审核通过的成绩可以直接更正")
        course = self.db.get(Course, g.course_id)
        if course is None:
            raise NotFound("课程不存在")

        score_updates = {
            k: v for k, v in updates.items() if k in self._SCORE_FIELDS
        }
        if not score_updates:
            raise Conflict("至少需要修改一项成绩字段")

        # 合并字段（mid_score/final_score）在实践课中只是计算结果回显，
        # 直接写入会被 ScoreService.compute 覆盖成理论/实践平均分，造成“更正成功但没变”。
        # 这里显式拒绝，避免静默无效操作；非实践课则拒绝拆分字段。
        profile = profile_for(course)
        for merged, parts, label in (
            ("mid_score", ("mid_theory_score", "mid_practice_score"), "期中"),
            ("final_score", ("final_theory_score", "final_practice_score"), "期末"),
        ):
            if profile.has_practice and merged in score_updates:
                raise Conflict(
                    f"该课程含实践学时，{label}请分别填写理论和实践成绩，"
                    f"不能直接修改合并成绩 {merged}"
                )
            if not profile.has_practice and any(p in score_updates for p in parts):
                raise Conflict(
                    f"该课程无实践学时，不能修改{label}理论/实践拆分成绩"
                )
            if not profile.has_midterm and any(
                p in score_updates for p in (merged, *parts)
            ) and merged.startswith("mid"):
                raise Conflict("该课程无期中考试，不能修改期中成绩")

        before = self._snapshot(g)
        try:
            for k, v in score_updates.items():
                setattr(g, k, v)
            ScoreService.compute(course, g)
        except Exception:
            self.db.rollback()
            raise

        g.status = GradeStatus.APPROVED
        g.approved_by = operator_id
        g.approved_at = datetime.now()
        g.reject_reason = None
        self._log_change(
            g, "CORRECT", reason, operator_id, before, self._snapshot(g)
        )
        self.db.flush()
        self._refresh_student_credits({g.student_id})
        self.db.commit()
        return g

    def _refresh_student_credits(self, student_ids: set[int]) -> None:
        """重算已修学分与 GPA（学分只计及格课程；GPA 由 GpaService 统一口径）。"""
        for sid in sorted(student_ids):
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
            # GPA 单一来源（DATABASE.md §9.3）：与 /grades/my、排名同口径，不及格计入 0.0
            try:
                gpa = GpaService(self.db).gpa_of(sid)
            except GpaError:
                # 无有效成绩或存在脏数据时置空，不阻断成绩状态变更。
                gpa = None
            stu = self.db.execute(
                select(Student).where(Student.id == sid).with_for_update()
            ).scalar_one_or_none()
            if stu:
                stu.total_credits = total_credits
                stu.gpa = gpa
        # 不在此处提交：由调用方与成绩状态变更放在同一事务内提交。

    # --- 学生侧 ---

    def list_by_student(self, student_id: int, semester: str | None = None) -> list[Grade]:
        """学生只能看到已审核通过的成绩（CLAUDE.md §18）。"""
        stmt = self.base_stmt().where(
            Grade.student_id == student_id, Grade.status == GradeStatus.APPROVED
        )
        if semester:
            stmt = stmt.where(Grade.semester == semester)
        return list(self.db.execute(stmt.order_by(Grade.semester.desc())).scalars())

    def student_overview(self, student: Student) -> dict:
        """学生成绩总览（TASK-007）：APPROVED 成绩 + 实时 GPA + 班级/专业排名。

        GPA 与排名均复用 TASK-004 的 GpaService / RankingService 实时计算，不落库；
        学生无任何有效成绩时，gpa / 排名返回 None。
        """
        grades = self.list_by_student(student.id)

        gpa = None
        try:
            gpa = GpaService(self.db).gpa_of(student.id)
        except NoGradesError:
            pass

        ranking = RankingService(self.db)
        class_rank = next(
            (
                r.ranking
                for r in ranking.class_ranking(student.class_id)
                if r.student_id == student.id
            ),
            None,
        )
        major_rank = next(
            (
                r.ranking
                for r in ranking.major_ranking(student.major_id)
                if r.student_id == student.id
            ),
            None,
        )

        return {
            "grades": grades,
            "gpa": gpa,
            "class_rank": class_rank,
            "major_rank": major_rank,
        }

    def pending_approval(self, semester: str | None = None) -> list[Grade]:
        stmt = self.base_stmt().where(Grade.status == GradeStatus.SUBMITTED)
        if semester:
            stmt = stmt.where(Grade.semester == semester)
        return list(self.db.execute(stmt).scalars())

    def student_summary(self, student_id: int) -> dict:
        rows = self.list_by_student(student_id)
        passed = [r for r in rows if r.is_passed]
        total = sum((Decimal(str(r.credits)) for r in passed), Decimal("0"))
        # GPA 单一来源（DATABASE.md §9.3）：与 /grades/my、排名同口径（不及格计入 0.0）
        try:
            gpa = GpaService(self.db).gpa_of(student_id)
        except NoGradesError:
            gpa = None
        return {
            "total_courses": len(rows),
            "passed_courses": len(passed),
            "failed_courses": len(rows) - len(passed),
            "total_credits": float(total),
            "gpa": float(gpa) if gpa is not None else None,
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
