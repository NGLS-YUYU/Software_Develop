"""FIX-006 学期管理真实 HTTP + MySQL 验收（不经过浏览器）。

对运行中的后端发真实 HTTP 请求，每一步都回查 MySQL 确认落库结果。

前置：uvicorn app.main:app --port 8000
用法：.venv/bin/python scripts/e2e_fix006_api.py
"""

import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.term import AcademicTerm, TermStatus  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
SEED_YEAR, SEED_SEM = "2026-2027", 1
E2E_YEAR, E2E_SEM = "2999-3000", 1
E2E_NAME = "FIX006-E2E-学期"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    results.append((bool(cond), label))
    print(f"  {'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")


def login(client: httpx.Client, u: str, p: str) -> dict:
    r = client.post(f"{BASE}/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def row(year: str, sem: int) -> AcademicTerm | None:
    with SessionLocal() as db:
        return db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == year, AcademicTerm.semester == sem
            )
        ).scalar_one_or_none()


def set_seed_active(active: bool) -> None:
    """单激活约束下的测试装置准备/还原（与 test_academic_term.py 同一手法）。"""
    with SessionLocal() as db:
        t = db.execute(
            select(AcademicTerm).where(
                AcademicTerm.academic_year == SEED_YEAR,
                AcademicTerm.semester == SEED_SEM,
            )
        ).scalar_one_or_none()
        if t is not None:
            t.status = TermStatus.ACTIVE if active else TermStatus.PLANNED
            db.commit()


def cleanup() -> None:
    from sqlalchemy import delete

    with SessionLocal() as db:
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like("FIX006-E2E%")))
        db.commit()


def main() -> int:
    cleanup()
    set_seed_active(True)
    try:
        with httpx.Client(timeout=20) as c:
            admin = login(c, "admin", "admin123")
            teacher = login(c, "T001", "T001")
            student = login(c, "20260001", "20260001")

            # ---------- Case 1 读取 ----------
            print("\n[Case 1] 读取真实学期列表")
            r = c.get(f"{BASE}/terms", headers=admin)
            check(r.status_code == 200, "GET /terms → 200")
            items = r.json()["items"]
            seeded = next((x for x in items if x["academic_year"] == SEED_YEAR), None)
            check(seeded is not None, "列表包含 MySQL 中的演示学期")
            check(seeded and seeded["status"] == "ACTIVE",
                  "状态与 MySQL 一致（ACTIVE）", seeded["status"] if seeded else "?")
            check(all("teaching_class_count" in x for x in items),
                  "列表返回教学班数量字段")

            # ---------- Case 2 新增 ----------
            print("\n[Case 2] 新增学期")
            payload = {
                "name": E2E_NAME, "academic_year": E2E_YEAR, "semester": E2E_SEM,
                "start_date": "2999-09-01", "end_date": "3000-01-15",
            }
            r = c.post(f"{BASE}/terms", json=payload, headers=admin)
            check(r.status_code == 201, "POST /terms → 201", r.text[:120])
            tid = r.json()["id"]
            check(r.json()["status"] == "PLANNED", "新学期待激活状态")
            db_row = row(E2E_YEAR, E2E_SEM)
            check(db_row is not None and db_row.id == tid,
                  "MySQL：academic_terms 出现新记录", f"id={db_row.id if db_row else '?'}")
            check(db_row and db_row.start_date == date(2999, 9, 1)
                  and db_row.end_date == date(3000, 1, 15), "MySQL：起止日期正确")

            # 重复新增（同一学年+学期）→ 409
            r = c.post(f"{BASE}/terms", json=payload, headers=admin)
            check(r.status_code == 409, "重复学年学期 → 409", r.json().get("message", ""))

            # 非法日期 → 422
            bad = dict(payload, academic_year="2998-2999",
                       start_date="2999-09-01", end_date="2999-08-01")
            r = c.post(f"{BASE}/terms", json=bad, headers=admin)
            check(r.status_code == 422, "结束日期早于开始日期 → 422")

            # ---------- 查询/筛选 ----------
            print("\n[筛选] 关键词 + 状态 + 分页")
            r = c.get(f"{BASE}/terms", params={"keyword": E2E_NAME}, headers=admin)
            check([x["id"] for x in r.json()["items"]] == [tid], "关键词搜索命中新学期")
            r = c.get(f"{BASE}/terms", params={"status": "PLANNED"}, headers=admin)
            check(tid in {x["id"] for x in r.json()["items"]}, "状态筛选 PLANNED 命中")
            r = c.get(f"{BASE}/terms",
                      params={"keyword": "FIX006", "page": 1, "page_size": 1},
                      headers=admin)
            check(r.json()["total"] == 1 and len(r.json()["items"]) == 1,
                  "分页由后端返回（page_size=1）", str(r.json()["total"]))

            # ---------- Case 5（前置）单激活约束 ----------
            print("\n[Case 5] 非法操作")
            r = c.post(f"{BASE}/terms/{tid}/activate", headers=admin)
            check(r.status_code == 409 and "进行中" in r.json()["message"],
                  "已有进行中学期时激活 → 409", r.json().get("message", ""))
            check(row(E2E_YEAR, E2E_SEM).status == "PLANNED", "MySQL：被拒绝后状态未变")

            # ---------- Case 3 激活 ----------
            print("\n[Case 3] 激活学期")
            set_seed_active(False)
            r = c.post(f"{BASE}/terms/{tid}/activate", headers=admin)
            check(r.status_code == 200 and r.json()["status"] == "ACTIVE",
                  "POST activate → ACTIVE")
            check(row(E2E_YEAR, E2E_SEM).status == "ACTIVE", "MySQL：状态为 ACTIVE")
            check(row(SEED_YEAR, SEED_SEM).status == "PLANNED",
                  "MySQL：原演示学期已被降级（单激活规则）")
            r = c.post(f"{BASE}/terms/{tid}/activate", headers=admin)
            check(r.status_code == 200, "重复激活幂等返回 200（前端按状态隐藏按钮）")

            # ---------- Case 4 结束 ----------
            print("\n[Case 4] 结束学期")
            r = c.post(f"{BASE}/terms/{tid}/end", headers=admin)
            check(r.status_code == 200 and r.json()["status"] == "ENDED",
                  "POST end → ENDED")
            check(row(E2E_YEAR, E2E_SEM).status == "ENDED", "MySQL：状态为 ENDED")
            r = c.post(f"{BASE}/terms/{tid}/end", headers=admin)
            check(r.status_code == 409 and "进行中" in r.json()["message"],
                  "已结束学期再次结束 → 409", r.json().get("message", ""))
            r = c.post(f"{BASE}/terms/{tid}/activate", headers=admin)
            check(r.status_code == 409 and "已结束" in r.json()["message"],
                  "已结束学期不可激活 → 409", r.json().get("message", ""))
            r = c.put(f"{BASE}/terms/{tid}", json={"status": "PLANNED"}, headers=admin)
            check(r.status_code == 409, "已结束学期不可改状态 → 409")

            # ---------- 权限 ----------
            print("\n[权限] 教师 / 学生")
            for h, label in ((teacher, "教师"), (student, "学生")):
                check(c.get(f"{BASE}/terms", headers=h).status_code == 200,
                      f"{label}可读学期列表（term:read）")
                check(c.post(f"{BASE}/terms", json=payload, headers=h).status_code == 403,
                      f"{label}新增 → 403")
                check(c.put(f"{BASE}/terms/{tid}", json={"name": "x"},
                            headers=h).status_code == 403, f"{label}编辑 → 403")
                check(c.delete(f"{BASE}/terms/{tid}", headers=h).status_code == 403,
                      f"{label}删除 → 403")
                check(c.post(f"{BASE}/terms/{tid}/activate",
                             headers=h).status_code == 403, f"{label}激活 → 403")
                check(c.post(f"{BASE}/terms/{tid}/end", headers=h).status_code == 403,
                      f"{label}结束 → 403")
            check(c.get(f"{BASE}/terms").status_code == 401, "未登录 → 401")

            # ---------- 清理 ----------
            print("\n[清理]")
            set_seed_active(True)
            r = c.delete(f"{BASE}/terms/{tid}", headers=admin)
            check(r.status_code == 204, "DELETE /terms/{id} → 204")
            check(row(E2E_YEAR, E2E_SEM) is None, "MySQL：E2E 学期已删除")
            check(row(SEED_YEAR, SEED_SEM).status == "ACTIVE",
                  "MySQL：演示学期已还原为 ACTIVE")
    finally:
        cleanup()
        set_seed_active(True)

    passed = sum(1 for ok, _ in results if ok)
    print(f"\n{'=' * 60}\nHTTP+MySQL E2E：{passed}/{len(results)} 通过")
    for ok, label in results:
        if not ok:
            print(f"  ❌ {label}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
