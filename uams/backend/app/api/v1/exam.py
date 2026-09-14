"""考试路由。"""

from datetime import date, time

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RequirePermissions, get_current_user
from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.db.session import get_db
from app.models.exam import Exam, ExamRoom, ExamStudent
from app.models.organization import Classroom
from app.models.person import Student
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.models.user import User, UserType
from app.schemas.common import PageParams, PageResult

router = APIRouter(prefix="/exams", tags=["考试"])


class ExamCreate(BaseModel):
    teaching_class_id: int
    exam_type: str = Field("FINAL", pattern="^(FINAL|MAKEUP|RETAKE)$")
    exam_date: date
    start_time: time
    end_time: time
    duration_minutes: int = Field(..., ge=10, le=480)

    @model_validator(mode="after")
    def check_time(self):
        if self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class ExamUpdate(BaseModel):
    exam_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = Field(None, ge=10, le=480)
    status: str | None = Field(None, pattern="^(DRAFT|PUBLISHED|FINISHED)$")


class ExamRoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exam_id: int
    classroom_id: int
    classroom_code: str | None = None
    building: str | None = None
    capacity: int
    assigned_count: int


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    teaching_class_id: int
    teaching_class_code: str | None = None
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    semester: str
    exam_type: str
    exam_date: date
    start_time: time
    end_time: time
    duration_minutes: int
    status: str
    rooms: list[ExamRoomOut] = []


class ExamRoomCreate(BaseModel):
    classroom_id: int
    capacity: int = Field(..., gt=0, le=500)
    invigilator_id: int | None = None


class MyExamOut(ExamOut):
    classroom_code: str | None = None
    seat_no: int | None = None


def _room_out(r) -> ExamRoomOut:
    d = ExamRoomOut.model_validate(r)
    if r.classroom:
        d.classroom_code, d.building = r.classroom.code, r.classroom.building
    return d


def _exam_out(e) -> ExamOut:
    d = ExamOut.model_validate(e)
    if e.course:
        d.course_code, d.course_name = e.course.code, e.course.name
    if e.teaching_class:
        d.teaching_class_code = e.teaching_class.code
    d.rooms = [_room_out(r) for r in e.rooms]
    return d


def _stmt():
    return select(Exam).options(
        selectinload(Exam.course),
        selectinload(Exam.teaching_class),
        selectinload(Exam.rooms).selectinload(ExamRoom.classroom),
    )


@router.get("", response_model=PageResult[ExamOut], summary="考试列表")
def list_exams(
    params: PageParams = Depends(),
    semester: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:read")),
):
    from sqlalchemy import func

    stmt = _stmt()
    if semester:
        stmt = stmt.where(Exam.semester == semester)
    if status_:
        stmt = stmt.where(Exam.status == status_)
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar() or 0
    rows = db.execute(
        stmt.order_by(Exam.exam_date, Exam.start_time)
        .offset(params.offset)
        .limit(params.page_size)
    ).scalars()
    return PageResult.build([_exam_out(e) for e in rows], total, params)


@router.get("/mine", response_model=list[MyExamOut], summary="我的考试安排")
def my_exams(
    semester: str | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """学生查看本人考试；只显示已发布的（PRD §7.4）。"""
    if current.user_type != UserType.STUDENT:
        raise PermissionDenied("当前账号不是学生")
    stu = db.execute(
        select(Student).where(Student.user_id == current.id)
    ).scalar_one_or_none()
    if stu is None:
        raise PermissionDenied("学生档案不存在")

    # 已选教学班 -> 已发布考试
    tc_ids = select(CourseSelection.teaching_class_id).where(
        CourseSelection.student_id == stu.id,
        CourseSelection.status == SelectionState.SELECTED,
    )
    stmt = _stmt().where(
        Exam.teaching_class_id.in_(tc_ids), Exam.status == "PUBLISHED"
    )
    if semester:
        stmt = stmt.where(Exam.semester == semester)

    out = []
    for e in db.execute(stmt.order_by(Exam.exam_date)).scalars():
        d = MyExamOut.model_validate(_exam_out(e).model_dump())
        # 查本人被分到的考场与座位
        es = db.execute(
            select(ExamStudent)
            .join(ExamRoom, ExamStudent.exam_room_id == ExamRoom.id)
            .where(ExamRoom.exam_id == e.id, ExamStudent.student_id == stu.id)
        ).scalar_one_or_none()
        if es:
            room = db.get(ExamRoom, es.exam_room_id)
            if room and room.classroom:
                d.classroom_code = room.classroom.code
            d.seat_no = es.seat_no
        out.append(d)
    return out


@router.post(
    "", response_model=ExamOut, status_code=status.HTTP_201_CREATED, summary="创建考试"
)
def create_exam(
    payload: ExamCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    tc = db.get(TeachingClass, payload.teaching_class_id)
    if tc is None:
        raise NotFound("教学班不存在")
    if db.execute(
        select(Exam).where(
            Exam.teaching_class_id == tc.id, Exam.exam_type == payload.exam_type
        )
    ).scalar_one_or_none():
        raise Conflict(f"该教学班的{payload.exam_type}考试已存在")

    e = Exam(
        **payload.model_dump(), course_id=tc.course_id, semester=tc.semester
    )
    db.add(e)
    db.commit()
    return _exam_out(db.execute(_stmt().where(Exam.id == e.id)).scalar_one())


@router.put("/{exam_id}", response_model=ExamOut, summary="修改考试")
def update_exam(
    exam_id: int,
    payload: ExamUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    e = db.get(Exam, exam_id)
    if e is None:
        raise NotFound("考试不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(e, k, v)
    db.commit()
    return _exam_out(db.execute(_stmt().where(Exam.id == exam_id)).scalar_one())


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除考试")
def delete_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    e = db.get(Exam, exam_id)
    if e is None:
        raise NotFound("考试不存在")
    db.delete(e)
    db.commit()


@router.post("/{exam_id}/rooms", response_model=ExamRoomOut, summary="添加考场")
def add_room(
    exam_id: int,
    payload: ExamRoomCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    e = db.get(Exam, exam_id)
    if e is None:
        raise NotFound("考试不存在")
    room = db.get(Classroom, payload.classroom_id)
    if room is None:
        raise NotFound("教室不存在")
    if payload.capacity > room.capacity:
        raise Conflict(f"考场容量不能超过教室容量 {room.capacity}")
    if db.execute(
        select(ExamRoom).where(
            ExamRoom.exam_id == exam_id, ExamRoom.classroom_id == payload.classroom_id
        )
    ).scalar_one_or_none():
        raise Conflict("该教室已是本场考试的考场")

    er = ExamRoom(exam_id=exam_id, **payload.model_dump())
    db.add(er)
    db.commit()
    db.refresh(er)
    return _room_out(er)


@router.post("/{exam_id}/assign", summary="自动分配考场座位")
def assign_seats(
    exam_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    """把该教学班已选学生按顺序填入各考场。"""
    e = db.get(Exam, exam_id)
    if e is None:
        raise NotFound("考试不存在")
    rooms = list(
        db.execute(
            select(ExamRoom).where(ExamRoom.exam_id == exam_id).order_by(ExamRoom.id)
        ).scalars()
    )
    if not rooms:
        raise Conflict("尚未设置考场")

    students = list(
        db.execute(
            select(CourseSelection.student_id).where(
                CourseSelection.teaching_class_id == e.teaching_class_id,
                CourseSelection.status == SelectionState.SELECTED,
            )
        ).scalars()
    )
    if sum(r.capacity for r in rooms) < len(students):
        raise Conflict(
            f"考场总容量 {sum(r.capacity for r in rooms)} 不足以容纳 {len(students)} 名考生"
        )

    # 清旧分配，重新排
    for r in rooms:
        db.execute(ExamStudent.__table__.delete().where(ExamStudent.exam_room_id == r.id))
        r.assigned_count = 0
    db.flush()

    idx, seat = 0, 1
    for sid in students:
        while idx < len(rooms) and rooms[idx].assigned_count >= rooms[idx].capacity:
            idx += 1
            seat = 1
        room = rooms[idx]
        db.add(ExamStudent(exam_room_id=room.id, student_id=sid, seat_no=seat))
        room.assigned_count += 1
        seat += 1
    db.commit()
    return {
        "assigned": len(students),
        "rooms": [
            {"classroom_id": r.classroom_id, "assigned": r.assigned_count} for r in rooms
        ],
    }


@router.post("/{exam_id}/publish", response_model=ExamOut, summary="发布考试")
def publish(
    exam_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("exam:write")),
):
    e = db.get(Exam, exam_id)
    if e is None:
        raise NotFound("考试不存在")
    if not e.rooms:
        raise Conflict("尚未设置考场，无法发布")
    e.status = "PUBLISHED"
    db.commit()
    return _exam_out(db.execute(_stmt().where(Exam.id == exam_id)).scalar_one())
