"""调停课申请与审核（F-22）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RequirePermissions, get_current_user, is_admin_user
from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.db.session import get_db
from app.models.adjustment import AdjustmentStatus, AdjustmentType, ScheduleAdjustment
from app.models.person import Teacher
from app.models.teaching import Schedule, TeachingClass
from app.models.user import User, UserType
from app.services.teaching import ScheduleService

router = APIRouter(prefix="/schedule-adjustments", tags=["调停课"])


class AdjustmentCreate(BaseModel):
    teaching_class_id: int
    request_type: str = Field(..., pattern="^(CHANGE|CANCEL|ADD)$")
    schedule_id: int | None = None
    reason: str = Field(..., min_length=1, max_length=500)
    new_day_of_week: int | None = Field(None, ge=1, le=7)
    new_start_period: int | None = Field(None, ge=1, le=14)
    new_end_period: int | None = Field(None, ge=1, le=14)
    new_start_week: int | None = Field(None, ge=1, le=30)
    new_end_week: int | None = Field(None, ge=1, le=30)
    new_week_type: str | None = Field(None, pattern="^(ALL|ODD|EVEN)$")
    new_classroom_id: int | None = None

    @model_validator(mode="after")
    def check_new_time(self):
        if (
            self.new_start_period is not None
            and self.new_end_period is not None
            and self.new_end_period < self.new_start_period
        ):
            raise ValueError("结束节次不能早于开始节次")
        if (
            self.new_start_week is not None
            and self.new_end_week is not None
            and self.new_end_week < self.new_start_week
        ):
            raise ValueError("结束周不能早于开始周")
        return self


class AdjustmentReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    teaching_class_id: int
    teaching_class_code: str | None = None
    course_name: str | None = None
    schedule_id: int | None = None
    request_type: str
    reason: str
    new_day_of_week: int | None = None
    new_start_period: int | None = None
    new_end_period: int | None = None
    new_start_week: int | None = None
    new_end_week: int | None = None
    new_week_type: str | None = None
    new_classroom_id: int | None = None
    status: str
    requested_by: int | None = None
    requester_name: str | None = None
    reviewed_by: int | None = None
    review_reason: str | None = None
    created_at: datetime | None = None


def _out(a: ScheduleAdjustment) -> AdjustmentOut:
    d = AdjustmentOut.model_validate(a)
    if a.teaching_class:
        d.teaching_class_code = a.teaching_class.code
        d.course_name = a.teaching_class.course.name if a.teaching_class.course else None
    d.requester_name = a.requester.real_name if a.requester else None
    return d


def _stmt():
    return select(ScheduleAdjustment).options(
        selectinload(ScheduleAdjustment.teaching_class).selectinload(TeachingClass.course),
        selectinload(ScheduleAdjustment.requester),
    )


def _teacher(db: Session, user: User) -> Teacher | None:
    return db.execute(select(Teacher).where(Teacher.user_id == user.id)).scalar_one_or_none()


@router.post("", response_model=AdjustmentOut, status_code=status.HTTP_201_CREATED, summary="提交调停课申请")
def create_adjustment(
    payload: AdjustmentCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.user_type != UserType.TEACHER and not is_admin_user(current):
        raise PermissionDenied("只有教师可以提交调停课申请")
    tc = db.get(TeachingClass, payload.teaching_class_id)
    if tc is None:
        raise NotFound("教学班不存在")
    if not is_admin_user(current):
        me = _teacher(db, current)
        if me is None or tc.teacher_id != me.id:
            raise PermissionDenied("只能为本人的教学班申请调停课")
    if payload.request_type in (AdjustmentType.CHANGE, AdjustmentType.CANCEL):
        if payload.schedule_id is None:
            raise Conflict("调课/停课必须指定原排课记录")
        s = db.get(Schedule, payload.schedule_id)
        if s is None or s.teaching_class_id != tc.id:
            raise NotFound("排课记录不存在或不属于该教学班")
    if payload.request_type == AdjustmentType.ADD and not all([
        payload.new_day_of_week, payload.new_start_period, payload.new_end_period,
        payload.new_start_week, payload.new_end_week, payload.new_classroom_id,
    ]):
        raise Conflict("补课必须填写星期、节次、周次和教室")
    a = ScheduleAdjustment(
        **payload.model_dump(),
        status=AdjustmentStatus.PENDING,
        requested_by=current.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _out(db.execute(_stmt().where(ScheduleAdjustment.id == a.id)).scalar_one())


@router.get("/mine", response_model=list[AdjustmentOut], summary="我的调停课申请")
def my_adjustments(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.user_type != UserType.TEACHER:
        raise PermissionDenied("仅教师查看本人申请")
    me = _teacher(db, current)
    if me is None:
        return []
    rows = db.execute(
        _stmt().where(ScheduleAdjustment.requested_by == current.id)
        .order_by(ScheduleAdjustment.created_at.desc())
    ).scalars()
    return [_out(a) for a in rows]


@router.get("", response_model=list[AdjustmentOut], summary="调停课申请列表（教务）")
def list_adjustments(
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("schedule:write")),
):
    stmt = _stmt().order_by(ScheduleAdjustment.created_at.desc())
    if status_:
        stmt = stmt.where(ScheduleAdjustment.status == status_)
    return [_out(a) for a in db.execute(stmt).scalars()]


def _pending(db: Session, adjustment_id: int) -> ScheduleAdjustment:
    # 行级锁：防止并发审批同一申请导致排课被重复应用。
    a = db.execute(
        select(ScheduleAdjustment)
        .where(ScheduleAdjustment.id == adjustment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if a is None:
        raise NotFound("调停课申请不存在")
    if a.status != AdjustmentStatus.PENDING:
        raise Conflict("只有待审核的申请可以处理")
    return a


@router.post("/{adjustment_id}/approve", response_model=AdjustmentOut, summary="批准调停课")
def approve_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("schedule:write")),
):
    a = _pending(db, adjustment_id)
    svc = ScheduleService(db)
    try:
        if a.request_type == AdjustmentType.CANCEL:
            if a.schedule_id is None:
                raise Conflict("停课申请缺少排课记录")
            svc.delete(a.schedule_id, commit=False)
        elif a.request_type == AdjustmentType.ADD:
            svc.create({
                "teaching_class_id": a.teaching_class_id,
                "classroom_id": a.new_classroom_id,
                "day_of_week": a.new_day_of_week,
                "start_period": a.new_start_period,
                "end_period": a.new_end_period,
                "start_week": a.new_start_week,
                "end_week": a.new_end_week,
                "week_type": a.new_week_type or "ALL",
            }, commit=False)
        else:
            if a.schedule_id is None:
                raise Conflict("调课申请缺少排课记录")
            s = db.get(Schedule, a.schedule_id)
            if s is None:
                raise NotFound("原排课记录不存在")
            data = {
                "classroom_id": a.new_classroom_id or s.classroom_id,
                "day_of_week": a.new_day_of_week or s.day_of_week,
                "start_period": a.new_start_period or s.start_period,
                "end_period": a.new_end_period or s.end_period,
                "start_week": a.new_start_week or s.start_week,
                "end_week": a.new_end_week or s.end_week,
                "week_type": a.new_week_type or s.week_type,
            }
            svc.update(a.schedule_id, data, commit=False)
        a.status = AdjustmentStatus.APPROVED
        a.reviewed_by = current.id
        a.review_reason = "同意"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _out(db.execute(_stmt().where(ScheduleAdjustment.id == a.id)).scalar_one())


@router.post("/{adjustment_id}/reject", response_model=AdjustmentOut, summary="驳回调停课")
def reject_adjustment(
    adjustment_id: int,
    payload: AdjustmentReject,
    db: Session = Depends(get_db),
    current: User = Depends(RequirePermissions("schedule:write")),
):
    a = _pending(db, adjustment_id)
    a.status = AdjustmentStatus.REJECTED
    a.reviewed_by = current.id
    a.review_reason = payload.reason
    db.commit()
    return _out(db.execute(_stmt().where(ScheduleAdjustment.id == a.id)).scalar_one())
