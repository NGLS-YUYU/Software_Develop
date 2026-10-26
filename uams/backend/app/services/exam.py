"""考试业务校验（F-07/F-16/F-19）。

- 考试与考试：同教室、同学生、同监考教师的时间重叠；
- 考试与教学安排：按学期起始日期换算周次，检查同教学班/同教室的潜在排课冲突；
- 考场修改/删除：容量、已分配座位、监考教师校验。
"""
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.models.exam import Exam, ExamRoom, ExamStudent
from app.models.organization import Classroom
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass
from app.models.term import AcademicTerm


def _overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


class ExamService:
    def __init__(self, db: Session):
        self.db = db

    # --- 基础 ---

    @staticmethod
    def duration_minutes(start: time, end: time) -> int:
        return (
            end.hour * 60 + end.minute - (start.hour * 60 + start.minute)
        )

    def _term_for_semester(self, semester: str) -> AcademicTerm | None:
        parts = (semester or "").rsplit("-", 1)
        if len(parts) != 2 or parts[1] not in ("1", "2"):
            return None
        return self.db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == parts[0],
                AcademicTerm.semester == int(parts[1]),
            )
        ).scalar_one_or_none()

    # --- 冲突查询 ---

    def room_conflict(
        self,
        classroom_id: int,
        exam_date: date,
        start: time,
        end: time,
        exclude_exam_id: int | None = None,
    ) -> ExamRoom | None:
        stmt = (
            select(ExamRoom)
            .join(Exam, ExamRoom.exam_id == Exam.id)
            .where(
                ExamRoom.classroom_id == classroom_id,
                Exam.exam_date == exam_date,
                Exam.start_time < end,
                Exam.end_time > start,
            )
        )
        if exclude_exam_id is not None:
            stmt = stmt.where(Exam.id != exclude_exam_id)
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()

    def invigilator_conflict(
        self,
        invigilator_id: int | None,
        exam_date: date,
        start: time,
        end: time,
        exclude_room_id: int | None = None,
    ) -> ExamRoom | None:
        if invigilator_id is None:
            return None
        stmt = (
            select(ExamRoom)
            .join(Exam, ExamRoom.exam_id == Exam.id)
            .where(
                ExamRoom.invigilator_id == invigilator_id,
                Exam.exam_date == exam_date,
                Exam.start_time < end,
                Exam.end_time > start,
            )
        )
        if exclude_room_id is not None:
            stmt = stmt.where(ExamRoom.id != exclude_room_id)
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()

    def student_conflicts(
        self, exam: Exam, exam_date: date, start: time, end: time
    ) -> list[int]:
        target = set(
            self.db.execute(
                select(CourseSelection.student_id).where(
                    CourseSelection.teaching_class_id == exam.teaching_class_id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        if not target:
            return []
        other_class_ids = list(
            self.db.execute(
                select(Exam.teaching_class_id).where(
                    Exam.id != exam.id,
                    Exam.exam_date == exam_date,
                    Exam.start_time < end,
                    Exam.end_time > start,
                )
            ).scalars()
        )
        if not other_class_ids:
            return []
        other_students = set(
            self.db.execute(
                select(CourseSelection.student_id).where(
                    CourseSelection.teaching_class_id.in_(other_class_ids),
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        return sorted(target & other_students)

    def schedule_conflict(
        self, exam: Exam, exam_date: date, start: time, end: time
    ) -> Schedule | None:
        """考试与排课的“潜在”冲突（无节次-时间映射，按日期/周次/教室/教学班判断）。"""
        term = self._term_for_semester(exam.semester)
        if term is None:
            raise Conflict("考试所属学期不存在，无法校验排课冲突")
        if exam_date < term.start_date or exam_date > term.end_date:
            raise Conflict("考试日期不在所属学期范围内")
        week_no = (exam_date - term.start_date).days // 7 + 1
        weekday = exam_date.isoweekday()
        room_ids = [
            r.classroom_id
            for r in self.db.execute(
                select(ExamRoom).where(ExamRoom.exam_id == exam.id)
            ).scalars()
        ]
        conditions = [Schedule.teaching_class_id == exam.teaching_class_id]
        if room_ids:
            conditions.append(Schedule.classroom_id.in_(room_ids))
        stmt = select(Schedule).where(
            Schedule.semester == exam.semester,
            Schedule.day_of_week == weekday,
            Schedule.start_week <= week_no,
            Schedule.end_week >= week_no,
            *conditions,
        )
        rows = [
            s
            for s in self.db.execute(stmt).scalars()
            if s.week_type == "ALL"
            or (s.week_type == "ODD" and week_no % 2 == 1)
            or (s.week_type == "EVEN" and week_no % 2 == 0)
        ]
        return rows[0] if rows else None

    # --- 校验入口 ---

    def validate_exam_window(
        self,
        exam: Exam,
        exam_date: date,
        start: time,
        end: time,
        duration_minutes: int,
        *,
        check_schedule: bool = True,
    ) -> None:
        if end <= start:
            raise Conflict("结束时间必须晚于开始时间")
        if self.duration_minutes(start, end) != duration_minutes:
            raise Conflict("考试时长必须与开始/结束时间一致")
        if check_schedule:
            hit = self.schedule_conflict(exam, exam_date, start, end)
            if hit is not None:
                raise Conflict(
                    f"考试与排课存在潜在冲突：第 {hit.start_week}-{hit.end_week} 周"
                    f" 周{hit.day_of_week} 第 {hit.start_period}-{hit.end_period} 节"
                )
        conflicts = self.student_conflicts(exam, exam_date, start, end)
        if conflicts:
            raise Conflict(
                f"以下学生同一时间已有其他考试：{', '.join(str(x) for x in conflicts[:10])}"
            )
        for room in exam.rooms:
            hit = self.room_conflict(
                room.classroom_id, exam_date, start, end, exclude_exam_id=exam.id
            )
            if hit is not None:
                raise Conflict(
                    f"教室 {room.classroom.code if room.classroom else room.classroom_id} "
                    f"在同一时间已被其他考试占用"
                )
            inv = self.invigilator_conflict(
                room.invigilator_id, exam_date, start, end,
                exclude_room_id=room.id,
            )
            if inv is not None:
                raise Conflict("该监考教师在同一时间已有其他监考任务")

    def validate_room(
        self,
        exam: Exam,
        classroom_id: int,
        capacity: int,
        invigilator_id: int | None,
        *,
        exclude_room_id: int | None = None,
        assigned_count: int = 0,
    ) -> Classroom:
        room = self.db.get(Classroom, classroom_id)
        if room is None:
            raise NotFound("教室不存在")
        if room.status != "ACTIVE":
            raise Conflict(f"教室 {room.code} 当前不可用（{room.status}）")
        if capacity > room.capacity:
            raise Conflict(f"考场容量不能超过教室容量 {room.capacity}")
        if capacity < assigned_count:
            raise Conflict(f"考场容量不能小于已排考生数 {assigned_count}")
        if invigilator_id is not None:
            teacher = self.db.get(Teacher, invigilator_id)
            if teacher is None:
                raise NotFound("监考教师不存在")
        hit = self.room_conflict(
            classroom_id, exam.exam_date, exam.start_time, exam.end_time,
            exclude_exam_id=exam.id,
        )
        # 同一考试重复教室由唯一约束/接口再校验；这里只查其他考试。
        hit_room = self.db.execute(
            select(ExamRoom).where(
                ExamRoom.exam_id == exam.id,
                ExamRoom.classroom_id == classroom_id,
            )
        ).scalar_one_or_none()
        if hit_room is not None and (
            exclude_room_id is None or hit_room.id != exclude_room_id
        ):
            raise Conflict("该教室已是本场考试的考场")
        if hit is not None:
            raise Conflict("该教室在同一时间已被其他考试占用")
        inv = self.invigilator_conflict(
            invigilator_id, exam.exam_date, exam.start_time, exam.end_time,
            exclude_room_id=exclude_room_id,
        )
        if inv is not None:
            raise Conflict("该监考教师在同一时间已有其他监考任务")
        return room

    def delete_room(self, exam: Exam, room: ExamRoom) -> None:
        if room.exam_id != exam.id:
            raise NotFound("考场不存在")
        assigned = self.db.execute(
            select(ExamStudent.id).where(ExamStudent.exam_room_id == room.id).limit(1)
        ).scalar_one_or_none()
        if assigned is not None or room.assigned_count > 0:
            raise Conflict("该考场已分配考生，不能删除；请先重新排座或调整考场")
        self.db.delete(room)

    def ensure_no_student_exam_conflict(self, exam: Exam) -> None:
        conflicts = self.student_conflicts(
            exam, exam.exam_date, exam.start_time, exam.end_time
        )
        if conflicts:
            raise Conflict(
                f"以下学生同一时间已有其他考试：{', '.join(str(x) for x in conflicts[:10])}"
            )
