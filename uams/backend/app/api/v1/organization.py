"""基础数据路由：学院、专业、班级、教室。

读权限对所有登录用户开放；写权限需教务（CLAUDE.md §9）。
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.db.session import get_db
from app.schemas.common import PageParams, PageResult
from app.schemas.organization import (
    ClassCreate,
    ClassOut,
    ClassroomCreate,
    ClassroomOut,
    ClassroomUpdate,
    ClassUpdate,
    CollegeCreate,
    CollegeOut,
    CollegeUpdate,
    MajorCreate,
    MajorOut,
    MajorUpdate,
)
from app.services.organization import (
    ClassroomService,
    ClassService,
    CollegeService,
    MajorService,
)

router = APIRouter(tags=["基础数据"])

_read = Depends(get_current_user)


# =========================== 学院 ===========================
colleges = APIRouter(prefix="/colleges", tags=["基础数据-学院"])


@colleges.get("", response_model=PageResult[CollegeOut], summary="学院列表")
def list_colleges(
    params: PageParams = Depends(),
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = CollegeService(db).paginate(params, status=status_)
    return PageResult.build([CollegeOut.model_validate(i) for i in items], total, params)


@colleges.get("/{college_id}", response_model=CollegeOut, summary="学院详情")
def get_college(college_id: int, db: Session = Depends(get_db), _=_read):
    return CollegeOut.model_validate(CollegeService(db).get_or_404(college_id))


@colleges.post(
    "", response_model=CollegeOut, status_code=status.HTTP_201_CREATED, summary="新增学院"
)
def create_college(
    payload: CollegeCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("college:write")),
):
    return CollegeOut.model_validate(CollegeService(db).create(payload.model_dump()))


@colleges.put("/{college_id}", response_model=CollegeOut, summary="修改学院")
def update_college(
    college_id: int,
    payload: CollegeUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("college:write")),
):
    return CollegeOut.model_validate(
        CollegeService(db).update(college_id, payload.model_dump(exclude_unset=True))
    )


@colleges.delete(
    "/{college_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除学院"
)
def delete_college(
    college_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("college:write")),
):
    CollegeService(db).delete(college_id)


# =========================== 专业 ===========================
majors = APIRouter(prefix="/majors", tags=["基础数据-专业"])


def _major_out(m) -> MajorOut:
    d = MajorOut.model_validate(m)
    d.college_name = m.college.name if m.college else None
    return d


@majors.get("", response_model=PageResult[MajorOut], summary="专业列表")
def list_majors(
    params: PageParams = Depends(),
    college_id: int | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = MajorService(db).paginate(params, college_id=college_id, status=status_)
    return PageResult.build([_major_out(i) for i in items], total, params)


@majors.get("/{major_id}", response_model=MajorOut, summary="专业详情")
def get_major(major_id: int, db: Session = Depends(get_db), _=_read):
    return _major_out(MajorService(db).get_or_404(major_id))


@majors.post(
    "", response_model=MajorOut, status_code=status.HTTP_201_CREATED, summary="新增专业"
)
def create_major(
    payload: MajorCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("major:write")),
):
    return _major_out(MajorService(db).create(payload.model_dump()))


@majors.put("/{major_id}", response_model=MajorOut, summary="修改专业")
def update_major(
    major_id: int,
    payload: MajorUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("major:write")),
):
    return _major_out(
        MajorService(db).update(major_id, payload.model_dump(exclude_unset=True))
    )


@majors.delete("/{major_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除专业")
def delete_major(
    major_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("major:write")),
):
    MajorService(db).delete(major_id)


# =========================== 班级 ===========================
classes = APIRouter(prefix="/classes", tags=["基础数据-班级"])


def _class_out(c) -> ClassOut:
    d = ClassOut.model_validate(c)
    d.major_name = c.major.name if c.major else None
    return d


@classes.get("", response_model=PageResult[ClassOut], summary="班级列表")
def list_classes(
    params: PageParams = Depends(),
    major_id: int | None = Query(None),
    grade_year: int | None = Query(None),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = ClassService(db).paginate(
        params, major_id=major_id, grade_year=grade_year
    )
    return PageResult.build([_class_out(i) for i in items], total, params)


@classes.get("/{class_id}", response_model=ClassOut, summary="班级详情")
def get_class(class_id: int, db: Session = Depends(get_db), _=_read):
    return _class_out(ClassService(db).get_or_404(class_id))


@classes.post(
    "", response_model=ClassOut, status_code=status.HTTP_201_CREATED, summary="新增班级"
)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("class:write")),
):
    return _class_out(ClassService(db).create(payload.model_dump()))


@classes.put("/{class_id}", response_model=ClassOut, summary="修改班级")
def update_class(
    class_id: int,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("class:write")),
):
    return _class_out(
        ClassService(db).update(class_id, payload.model_dump(exclude_unset=True))
    )


@classes.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除班级")
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("class:write")),
):
    ClassService(db).delete(class_id)


# =========================== 教室 ===========================
classrooms = APIRouter(prefix="/classrooms", tags=["基础数据-教室"])


@classrooms.get("", response_model=PageResult[ClassroomOut], summary="教室列表")
def list_classrooms(
    params: PageParams = Depends(),
    building: str | None = Query(None),
    room_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _=_read,
):
    items, total = ClassroomService(db).paginate(
        params, building=building, room_type=room_type
    )
    return PageResult.build([ClassroomOut.model_validate(i) for i in items], total, params)


@classrooms.get("/{room_id}", response_model=ClassroomOut, summary="教室详情")
def get_classroom(room_id: int, db: Session = Depends(get_db), _=_read):
    return ClassroomOut.model_validate(ClassroomService(db).get_or_404(room_id))


@classrooms.post(
    "", response_model=ClassroomOut, status_code=status.HTTP_201_CREATED, summary="新增教室"
)
def create_classroom(
    payload: ClassroomCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("classroom:write")),
):
    return ClassroomOut.model_validate(ClassroomService(db).create(payload.model_dump()))


@classrooms.put("/{room_id}", response_model=ClassroomOut, summary="修改教室")
def update_classroom(
    room_id: int,
    payload: ClassroomUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("classroom:write")),
):
    return ClassroomOut.model_validate(
        ClassroomService(db).update(room_id, payload.model_dump(exclude_unset=True))
    )


@classrooms.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除教室")
def delete_classroom(
    room_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("classroom:write")),
):
    ClassroomService(db).delete(room_id)


for r in (colleges, majors, classes, classrooms):
    router.include_router(r)
