"""课程与培养方案路由。"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.db.session import get_db
from app.models.course import Course
from app.schemas.common import PageParams, PageResult
from app.schemas.course import (
    CourseCreate,
    CourseOut,
    CourseUpdate,
    CurriculumCourseCreate,
    CurriculumCourseOut,
    CurriculumPlanCreate,
    CurriculumPlanOut,
    CurriculumPlanUpdate,
    PrerequisiteCreate,
    PrerequisiteOut,
)
from app.services.course import CourseService, CurriculumService

router = APIRouter(tags=["课程"])
_read = Depends(get_current_user)


def _course_out(c) -> CourseOut:
    d = CourseOut.model_validate(c)
    d.college_name = c.college.name if c.college else None
    return d


# =========================== 课程 ===========================
courses = APIRouter(prefix="/courses", tags=["课程-课程管理"])


@courses.get("", response_model=PageResult[CourseOut], summary="课程列表")
def list_courses(
    params: PageParams = Depends(),
    college_id: int | None = Query(None),
    course_type: str | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = CourseService(db).paginate(
        params, college_id=college_id, course_type=course_type, status=status_
    )
    return PageResult.build([_course_out(i) for i in items], total, params)


@courses.get("/{course_id}", response_model=CourseOut, summary="课程详情")
def get_course(course_id: int, db: Session = Depends(get_db), _=_read):
    return _course_out(CourseService(db).get_or_404(course_id))


@courses.post(
    "", response_model=CourseOut, status_code=status.HTTP_201_CREATED, summary="新增课程"
)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("course:write")),
):
    return _course_out(CourseService(db).create(payload.model_dump()))


@courses.put("/{course_id}", response_model=CourseOut, summary="修改课程")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("course:write")),
):
    return _course_out(
        CourseService(db).update(course_id, payload.model_dump(exclude_unset=True))
    )


@courses.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除课程")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("course:write")),
):
    CourseService(db).delete(course_id)


# --- 先修课程 ---
@courses.get(
    "/{course_id}/prerequisites",
    response_model=list[PrerequisiteOut],
    summary="先修课程列表",
)
def list_prerequisites(course_id: int, db: Session = Depends(get_db), _=_read):
    svc = CourseService(db)
    out = []
    for p in svc.list_prerequisites(course_id):
        d = PrerequisiteOut.model_validate(p)
        pc = db.get(Course, p.prerequisite_course_id)
        if pc:
            d.prerequisite_code, d.prerequisite_name = pc.code, pc.name
        out.append(d)
    return out


@courses.post(
    "/{course_id}/prerequisites",
    response_model=PrerequisiteOut,
    status_code=status.HTTP_201_CREATED,
    summary="添加先修课程",
)
def add_prerequisite(
    course_id: int,
    payload: PrerequisiteCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("course:write")),
):
    obj = CourseService(db).add_prerequisite(
        course_id, payload.prerequisite_course_id, payload.min_score
    )
    return PrerequisiteOut.model_validate(obj)


@courses.delete(
    "/{course_id}/prerequisites/{row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除先修课程",
)
def remove_prerequisite(
    course_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("course:write")),
):
    CourseService(db).remove_prerequisite(course_id, row_id)


# =========================== 培养方案 ===========================
plans = APIRouter(prefix="/curriculum-plans", tags=["课程-培养方案"])


def _plan_out(p) -> CurriculumPlanOut:
    d = CurriculumPlanOut.model_validate(p)
    d.major_name = p.major.name if p.major else None
    return d


@plans.get("", response_model=PageResult[CurriculumPlanOut], summary="培养方案列表")
def list_plans(
    params: PageParams = Depends(),
    major_id: int | None = Query(None),
    grade_year: int | None = Query(None),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = CurriculumService(db).paginate(
        params, major_id=major_id, grade_year=grade_year
    )
    return PageResult.build([_plan_out(i) for i in items], total, params)


@plans.get("/{plan_id}", response_model=CurriculumPlanOut, summary="培养方案详情")
def get_plan(plan_id: int, db: Session = Depends(get_db), _=_read):
    return _plan_out(CurriculumService(db).get_or_404(plan_id))


@plans.post(
    "",
    response_model=CurriculumPlanOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增培养方案",
)
def create_plan(
    payload: CurriculumPlanCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("curriculum:write")),
):
    return _plan_out(CurriculumService(db).create(payload.model_dump()))


@plans.put("/{plan_id}", response_model=CurriculumPlanOut, summary="修改培养方案")
def update_plan(
    plan_id: int,
    payload: CurriculumPlanUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("curriculum:write")),
):
    return _plan_out(
        CurriculumService(db).update(plan_id, payload.model_dump(exclude_unset=True))
    )


@plans.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除培养方案")
def delete_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("curriculum:write")),
):
    CurriculumService(db).delete(plan_id)


@plans.get(
    "/{plan_id}/courses",
    response_model=list[CurriculumCourseOut],
    summary="方案课程列表",
)
def list_plan_courses(plan_id: int, db: Session = Depends(get_db), _=_read):
    out = []
    for cc in CurriculumService(db).list_courses(plan_id):
        d = CurriculumCourseOut.model_validate(cc)
        if cc.course:
            d.course_code, d.course_name, d.credits = (
                cc.course.code,
                cc.course.name,
                cc.course.credits,
            )
        out.append(d)
    return out


@plans.post(
    "/{plan_id}/courses",
    response_model=CurriculumCourseOut,
    status_code=status.HTTP_201_CREATED,
    summary="添加方案课程",
)
def add_plan_course(
    plan_id: int,
    payload: CurriculumCourseCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("curriculum:write")),
):
    obj = CurriculumService(db).add_course(
        plan_id, payload.course_id, payload.suggested_semester, payload.is_required
    )
    return CurriculumCourseOut.model_validate(obj)


@plans.delete(
    "/{plan_id}/courses/{row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="移除方案课程",
)
def remove_plan_course(
    plan_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("curriculum:write")),
):
    CurriculumService(db).remove_course(plan_id, row_id)


router.include_router(courses)
router.include_router(plans)
