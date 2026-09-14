"""课表路由：学生课表、教师课表。

课表由选课记录 + 排课自动生成（PRD §7.2），不单独存表。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass
from app.models.user import User, UserType

router = APIRouter(prefix="/schedules", tags=["课表"])

WEEKDAYS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


class ScheduleItem(BaseModel):
    schedule_id: int
    teaching_class_id: int
    teaching_class_code: str
    course_code: str | None = None
    course_name: str | None = None
    teacher_name: str | None = None
    classroom_code: str | None = None
    building: str | None = None
    day_of_week: int
    day_name: str
    start_period: int
    end_period: int
    start_week: int
    end_week: int
    week_type: str
    semester: str


def _item(s: Schedule, tc: TeachingClass) -> ScheduleItem:
    return ScheduleItem(
        schedule_id=s.id,
        teaching_class_id=tc.id,
        teaching_class_code=tc.code,
        course_code=tc.course.code if tc.course else None,
        course_name=tc.course.name if tc.course else None,
        teacher_name=tc.teacher.user.real_name
        if tc.teacher and tc.teacher.user
        else None,
        classroom_code=s.classroom.code if s.classroom else None,
        building=s.classroom.building if s.classroom else None,
        day_of_week=s.day_of_week,
        day_name=WEEKDAYS.get(s.day_of_week, ""),
        start_period=s.start_period,
        end_period=s.end_period,
        start_week=s.start_week,
        end_week=s.end_week,
        week_type=s.week_type,
        semester=s.semester,
    )


def _in_week(s: Schedule, week: int | None) -> bool:
    if week is None:
        return True
    if not (s.start_week <= week <= s.end_week):
        return False
    if s.week_type == "ODD":
        return week % 2 == 1
    if s.week_type == "EVEN":
        return week % 2 == 0
    return True


def _tc_stmt():
    return select(TeachingClass).options(
        selectinload(TeachingClass.course),
        selectinload(TeachingClass.teacher).selectinload(Teacher.user),
        selectinload(TeachingClass.schedules).selectinload(Schedule.classroom),
    )


@router.get("/mine", response_model=list[ScheduleItem], summary="我的课表")
def my_schedule(
    semester: str = Query(..., description="学期，如 2026-2027-1"),
    week: int | None = Query(None, ge=1, le=30, description="第几周，不填返回全部"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """学生返回已选课程课表；教师返回授课课表。"""
    if current.user_type == UserType.STUDENT:
        stu = db.execute(
            select(Student).where(Student.user_id == current.id)
        ).scalar_one_or_none()
        if stu is None:
            raise PermissionDenied("学生档案不存在")
        tc_ids = select(CourseSelection.teaching_class_id).where(
            CourseSelection.student_id == stu.id,
            CourseSelection.status == SelectionState.SELECTED,
            CourseSelection.semester == semester,
        )
        stmt = _tc_stmt().where(TeachingClass.id.in_(tc_ids))

    elif current.user_type == UserType.TEACHER:
        t = db.execute(
            select(Teacher).where(Teacher.user_id == current.id)
        ).scalar_one_or_none()
        if t is None:
            raise PermissionDenied("教师档案不存在")
        stmt = _tc_stmt().where(
            TeachingClass.teacher_id == t.id,
            TeachingClass.semester == semester,
            TeachingClass.status == "ACTIVE",
        )
    else:
        raise PermissionDenied("教务请使用教学班排课查询")

    out: list[ScheduleItem] = []
    for tc in db.execute(stmt).scalars():
        for s in tc.schedules:
            if _in_week(s, week):
                out.append(_item(s, tc))
    out.sort(key=lambda x: (x.day_of_week, x.start_period))
    return out


@router.get(
    "/students/{student_id}", response_model=list[ScheduleItem], summary="查看学生课表"
)
def student_schedule(
    student_id: int,
    semester: str = Query(...),
    week: int | None = Query(None, ge=1, le=30),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """教务/教师查看指定学生课表；学生只能查自己。"""
    stu = db.get(Student, student_id)
    if stu is None:
        raise PermissionDenied("学生不存在")
    if current.user_type == UserType.STUDENT and stu.user_id != current.id:
        raise PermissionDenied("只能查看本人课表")

    tc_ids = select(CourseSelection.teaching_class_id).where(
        CourseSelection.student_id == stu.id,
        CourseSelection.status == SelectionState.SELECTED,
        CourseSelection.semester == semester,
    )
    out: list[ScheduleItem] = []
    for tc in db.execute(_tc_stmt().where(TeachingClass.id.in_(tc_ids))).scalars():
        for s in tc.schedules:
            if _in_week(s, week):
                out.append(_item(s, tc))
    out.sort(key=lambda x: (x.day_of_week, x.start_period))
    return out
