"""学期路由（TASK-011）。"""

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import RequirePermissions, get_current_user
from app.db.session import get_db
from app.schemas.common import PageParams, PageResult
from app.schemas.term import TermCreate, TermOut, TermUpdate
from app.services.term import AcademicTermService

router = APIRouter(prefix="/terms", tags=["学期"])


def _term_out(t, svc: AcademicTermService) -> TermOut:
    d = TermOut.model_validate(t)
    d.teaching_class_count = svc.teaching_class_count(t.id)
    return d


@router.get("", response_model=PageResult[TermOut], summary="学期列表")
def list_terms(
    params: PageParams = Depends(),
    academic_year: str | None = Query(None, description="按学年过滤"),
    status: str | None = Query(None, description="按状态过滤"),
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:read")),
):
    svc = AcademicTermService(db)
    items, total = svc.paginate(params, academic_year=academic_year, status=status)
    return PageResult.build([_term_out(t, svc) for t in items], total, params)


@router.get("/active", response_model=TermOut, summary="当前进行中的学期")
def active_term(
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:read")),
):
    """全系统统一读取 ACTIVE 学期，避免前端按浏览器日期推断。"""
    svc = AcademicTermService(db)
    return _term_out(svc.active(), svc)


@router.get("/{term_id}", response_model=TermOut, summary="学期详情")
def get_term(
    term_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:read")),
):
    svc = AcademicTermService(db)
    return _term_out(svc.get_or_404(term_id), svc)


@router.post(
    "",
    response_model=TermOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="新增学期",
)
def create_term(
    payload: TermCreate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:write")),
):
    svc = AcademicTermService(db)
    t = svc.create(payload.model_dump())
    return _term_out(svc.get_or_404(t.id), svc)


@router.put("/{term_id}", response_model=TermOut, summary="修改学期")
def update_term(
    term_id: int,
    payload: TermUpdate,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:write")),
):
    svc = AcademicTermService(db)
    svc.update(term_id, payload.model_dump(exclude_unset=True))
    return _term_out(svc.get_or_404(term_id), svc)


@router.delete(
    "/{term_id}", status_code=http_status.HTTP_204_NO_CONTENT, summary="删除学期"
)
def delete_term(
    term_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:write")),
):
    AcademicTermService(db).delete(term_id)


@router.post("/{term_id}/activate", response_model=TermOut, summary="激活学期")
def activate_term(
    term_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:write")),
):
    svc = AcademicTermService(db)
    svc.activate(term_id)
    return _term_out(svc.get_or_404(term_id), svc)


@router.post("/{term_id}/end", response_model=TermOut, summary="结束学期")
def end_term(
    term_id: int,
    db: Session = Depends(get_db),
    _=Depends(RequirePermissions("term:write")),
):
    svc = AcademicTermService(db)
    svc.end(term_id)
    return _term_out(svc.get_or_404(term_id), svc)
