"""GPA 排名服务（TASK-004）。

支持班级/专业 GPA 排名。排名**实时计算**，不保存任何排名字段：
    Student + APPROVED 成绩 → gpa_service（逐人实时 GPA）→ 按 GPA 降序 → DTO
"""

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.grade import Grade, GradeStatus
from app.models.person import Student
from app.services.gpa_service import NoGradesError, student_gpa


class RankingItem(BaseModel):
    """排名结果 DTO（服务层返回，不落库）。"""

    student_id: int
    student_name: str
    gpa: Decimal
    ranking: int


class RankingService:
    def __init__(self, db: Session):
        self.db = db

    # --- 对外接口 ---

    def class_ranking(self, class_id: int) -> list[RankingItem]:
        students = self._students(Student.class_id == class_id)
        return self._rank(students)

    def major_ranking(self, major_id: int) -> list[RankingItem]:
        students = self._students(Student.major_id == major_id)
        return self._rank(students)

    # --- 内部实现 ---

    def _students(self, *conditions) -> list[Student]:
        stmt = select(Student).options(selectinload(Student.user))
        for cond in conditions:
            stmt = stmt.where(cond)
        return list(self.db.execute(stmt).scalars())

    def _gpa_map(self, student_ids: list[int]) -> dict[int, Decimal]:
        """批量读取成绩并逐人实时计算 GPA；无有效成绩的学生不参与排名。"""
        if not student_ids:
            return {}
        rows = self.db.execute(
            select(Grade.student_id, Grade.credits, Grade.total_score).where(
                Grade.student_id.in_(student_ids),
                Grade.status == GradeStatus.APPROVED,
                Grade.total_score.is_not(None),
            )
        ).all()
        grouped: dict[int, list[tuple[Decimal, Decimal]]] = {}
        for sid, credit, score in rows:
            grouped.setdefault(sid, []).append(
                (Decimal(str(credit)), Decimal(str(score)))
            )
        result: dict[int, Decimal] = {}
        for sid, entries in grouped.items():
            try:
                result[sid] = student_gpa(entries)
            except NoGradesError:
                continue
        return result

    def _rank(self, students: list[Student]) -> list[RankingItem]:
        gpas = self._gpa_map([s.id for s in students])
        ranked = sorted(
            (s for s in students if s.id in gpas),
            key=lambda s: gpas[s.id],
            reverse=True,
        )
        items: list[RankingItem] = []
        prev_gpa: Decimal | None = None
        rank = 0
        for i, s in enumerate(ranked, 1):
            gpa = gpas[s.id]
            if gpa != prev_gpa:
                rank = i  # 同分并列，下一名次跳号（1,2,2,4）
            items.append(
                RankingItem(
                    student_id=s.id,
                    student_name=s.user.real_name if s.user else "",
                    gpa=gpa,
                    ranking=rank,
                )
            )
            prev_gpa = gpa
        return items
