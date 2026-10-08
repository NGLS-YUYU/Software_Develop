"""FIX-007 排课真实 HTTP + MySQL 验收（TASK-013 平铺接口）。

覆盖：新增排课 / 修改排课 / 三类冲突拒绝 / 教师课表 / 学生课表 /
周次过滤 / 数据权限 / 越权拒绝，每一步回查 MySQL。

隔离策略：全部排课使用独立学期字符串 ``2099-2099-1``，与演示数据互不影响。

前置：./start.sh start（后端 :8000）
用法：.venv/bin/python scripts/e2e_fix007_schedule.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.grade import Grade  # noqa: E402
from app.models.organization import Class, Classroom, College, Major  # noqa: E402
from app.models.person import Student, Teacher  # noqa: E402
from app.models.role import Role, RoleCode, UserRole  # noqa: E402
from app.models.selection import CourseSelection, SelectionState  # noqa: E402
from app.models.teaching import Schedule, TeachingClass, TeachingTask  # noqa: E402
from app.models.term import AcademicTerm  # noqa: E402
from app.models.user import User, UserType  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
P = "E2E7"
SEM = "2099-2099-1"
PWD = "e2e7test123"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    results.append((bool(cond), label))
    print(f"  {'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")


def login(c: httpx.Client, u: str, p: str) -> dict:
    r = c.post(f"{BASE}/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def cleanup() -> None:
    with SessionLocal() as db:
        courses = select(Course.id).where(Course.code.like(f"{P}%"))
        tcs = select(TeachingClass.id).where(TeachingClass.code.like(f"{P}%"))
        students = select(Student.id).where(Student.student_no.like(f"{P}%"))
        db.execute(delete(Grade).where(Grade.teaching_class_id.in_(tcs)))
        db.execute(delete(CourseSelection).where(CourseSelection.teaching_class_id.in_(tcs)))
        db.execute(delete(Schedule).where(Schedule.teaching_class_id.in_(tcs)))
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{P}%")))
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{P}%")))
        db.execute(delete(TeachingTask).where(TeachingTask.course_id.in_(courses)))
        db.execute(delete(Student).where(Student.student_no.like(f"{P}%")))
        db.execute(delete(Teacher).where(Teacher.teacher_no.like(f"{P}%")))
        db.execute(delete(User).where(User.username.like(f"{P}%")))
        db.execute(delete(Class).where(Class.code.like(f"{P}%")))
        db.execute(delete(Major).where(Major.code.like(f"{P}%")))
        db.execute(delete(Classroom).where(Classroom.code.like(f"{P}%")))
        db.execute(delete(Course).where(Course.code.like(f"{P}%")))
        db.execute(delete(College).where(College.code.like(f"{P}%")))
        db.commit()


def setup() -> dict:
    cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}COL", name="E2E7学院")
        db.add(college); db.flush()
        major = Major(code=f"{P}MAJ", name="E2E7专业", college_id=college.id)
        db.add(major); db.flush()
        klass = Class(code=f"{P}CLS", name="E2E7班", major_id=major.id, grade_year=2026)
        db.add(klass); db.flush()
        term = AcademicTerm(
            name=f"{P}学期", academic_year="2099-2100", semester=1,
            start_date=date(2099, 9, 1), end_date=date(2100, 1, 15),
            status="PLANNED",
        )
        db.add(term); db.flush()
        course = Course(
            code=f"{P}C1", name="E2E7课程", college_id=college.id,
            course_type="REQUIRED", credits=Decimal("3.0"),
            total_hours=48, theory_hours=48, practice_hours=0,
        )
        db.add(course); db.flush()
        task = TeachingTask(
            semester=SEM, course_id=course.id, college_id=college.id,
            status="CONFIRMED",
        )
        db.add(task); db.flush()

        room1 = Classroom(code=f"{P}R1", building="E2E楼", capacity=60, room_type="NORMAL")
        room2 = Classroom(code=f"{P}R2", building="E2E楼", capacity=60, room_type="NORMAL")
        room3 = Classroom(code=f"{P}R3", building="E2E楼", capacity=60, room_type="NORMAL")
        db.add_all([room1, room2, room3]); db.flush()

        role_t = db.execute(select(Role).where(Role.code == RoleCode.TEACHER)).scalar_one()
        role_s = db.execute(select(Role).where(Role.code == RoleCode.STUDENT)).scalar_one()

        def mk_user(username, real_name, utype, role):
            u = User(username=username, password_hash=__import__(
                "app.core.security", fromlist=["hash_password"]
            ).hash_password(PWD), real_name=real_name, user_type=utype)
            db.add(u); db.flush()
            db.add(UserRole(user_id=u.id, role_id=role.id)); db.flush()
            return u

        t1u = mk_user(f"{P}T1", "E2E7教师甲", UserType.TEACHER, role_t)
        t1 = Teacher(user_id=t1u.id, teacher_no=f"{P}T1", college_id=college.id)
        t2u = mk_user(f"{P}T2", "E2E7教师乙", UserType.TEACHER, role_t)
        t2 = Teacher(user_id=t2u.id, teacher_no=f"{P}T2", college_id=college.id)
        db.add_all([t1, t2]); db.flush()

        s_u = mk_user(f"{P}S1", "E2E7学生", UserType.STUDENT, role_s)
        stu = Student(
            user_id=s_u.id, student_no=f"{P}S1", class_id=klass.id,
            major_id=major.id, college_id=college.id, enrollment_year=2026,
        )
        db.add(stu); db.flush()

        def mk_tc(code, teacher):
            tc = TeachingClass(
                code=f"{P}{code}", task_id=task.id, course_id=course.id,
                semester=SEM, teacher_id=teacher.id, capacity=50, term_id=term.id,
            )
            db.add(tc); db.flush()
            return tc

        tc_a = mk_tc("TCA", t1)   # 教师甲
        tc_b = mk_tc("TCB", t2)   # 教师乙
        tc_c = mk_tc("TCC", t1)   # 教师甲（用于教师冲突）

        # 学生只选 TCA → 学生课表只能看到 TCA 的排课
        db.add(CourseSelection(
            student_id=stu.id, teaching_class_id=tc_a.id, course_id=course.id,
            semester=SEM, status=SelectionState.SELECTED,
        ))
        db.commit()
        return {
            "tc_a": tc_a.id, "tc_b": tc_b.id, "tc_c": tc_c.id,
            "tc_a_code": tc_a.code, "tc_b_code": tc_b.code, "tc_c_code": tc_c.code,
            "room1": room1.id, "room2": room2.id, "room3": room3.id,
            "room1_code": room1.code, "room2_code": room2.code, "room3_code": room3.code,
            "t1": f"{P}T1", "t2": f"{P}T2", "s1": f"{P}S1",
            "t1_id": t1.id, "s1_id": stu.id,
        }


def sched_row(sid: int) -> Schedule | None:
    with SessionLocal() as db:
        return db.get(Schedule, sid)


def count_schedules(tc_id: int) -> int:
    with SessionLocal() as db:
        return len(list(db.execute(
            select(Schedule).where(Schedule.teaching_class_id == tc_id)
        ).scalars()))


def main() -> int:
    env = setup()
    try:
        with httpx.Client(timeout=25) as c:
            admin = login(c, "admin", "admin123")
            t1 = login(c, env["t1"], PWD)
            t2 = login(c, env["t2"], PWD)
            stu = login(c, env["s1"], PWD)

            # ---------- Case A：新增成功 ----------
            print("\n[Case A] 新增排课")
            payload = {
                "teaching_class_id": env["tc_a"], "classroom_id": env["room1"],
                "day_of_week": 1, "start_period": 1, "end_period": 2,
                "start_week": 1, "end_week": 16, "week_type": "ALL",
            }
            r = c.post(f"{BASE}/teaching-schedules", json=payload, headers=admin)
            check(r.status_code == 201, "POST /teaching-schedules → 201", r.text[:150])
            sid = r.json()["id"]
            check(r.json()["teaching_class_code"] == env["tc_a_code"],
                  "响应带教学班编号", r.json().get("teaching_class_code"))
            row = sched_row(sid)
            check(row is not None and row.classroom_id == env["room1"],
                  "MySQL：schedules 新增记录")
            check(row.semester == SEM, "MySQL：学期取自教学班", row.semester if row else "?")

            # 页面刷新仍存在（重新查询）
            lst = c.get(f"{BASE}/teaching-schedules",
                        params={"teaching_class_id": env["tc_a"]}, headers=admin).json()
            check([x["id"] for x in lst] == [sid], "按教学班过滤可查到该排课")

            # ---------- Case B：修改成功 ----------
            print("\n[Case B] 修改排课")
            r = c.put(f"{BASE}/teaching-schedules/{sid}",
                      json={"classroom_id": env["room2"], "day_of_week": 3,
                            "start_period": 5, "end_period": 6},
                      headers=admin)
            check(r.status_code == 200, "PUT /teaching-schedules/{id} → 200", r.text[:150])
            row = sched_row(sid)
            check(row.classroom_id == env["room2"] and row.day_of_week == 3
                  and row.start_period == 5, "MySQL：教室/星期/节次已更新",
                  f"room={row.classroom_id} day={row.day_of_week} p={row.start_period}")
            check(row.classroom_id != env["room1"], "MySQL：旧教室已被替换")

            # 教师课表同步更新
            mine = c.get(f"{BASE}/teaching-schedules/mine",
                         params={"semester": SEM}, headers=t1).json()
            hit = next((x for x in mine if x["id"] == sid), None)
            check(hit is not None and hit["classroom_code"] == env["room2_code"],
                  "教师课表反映修改后的教室", hit["classroom_code"] if hit else "未找到")
            # 学生课表同步更新
            my = c.get(f"{BASE}/teaching-schedules/my",
                       params={"semester": SEM}, headers=stu).json()
            sh = next((x for x in my if x["id"] == sid), None)
            check(sh is not None and sh["day_of_week"] == 3,
                  "学生课表反映修改后的时间", f"day={sh['day_of_week']}" if sh else "未找到")

            # ---------- Case C：三类冲突 ----------
            print("\n[Case C] 三类冲突")
            base = dict(payload, day_of_week=3, start_period=5, end_period=6,
                        start_week=1, end_week=16, week_type="ALL")
            # 教师冲突：TCC 同为教师甲，同一时段
            r = c.post(f"{BASE}/teaching-schedules",
                       json=dict(base, teaching_class_id=env["tc_c"],
                                 classroom_id=env["room3"]), headers=admin)
            check(r.status_code == 409 and "TEACHER" in r.json().get("code", ""),
                  "教师冲突 → 409 TEACHER_CONFLICT",
                  f"{r.status_code} {r.json().get('code')}")
            check(count_schedules(env["tc_c"]) == 0, "MySQL：教师冲突未产生排课")

            # 教室冲突：TCB 用同一教室同一时段（教师不同）
            r = c.post(f"{BASE}/teaching-schedules",
                       json=dict(base, teaching_class_id=env["tc_b"],
                                 classroom_id=env["room2"]), headers=admin)
            check(r.status_code == 409 and "CLASSROOM" in r.json().get("code", ""),
                  "教室冲突 → 409 CLASSROOM_CONFLICT",
                  f"{r.status_code} {r.json().get('code')}")
            check(count_schedules(env["tc_b"]) == 0, "MySQL：教室冲突未产生排课")

            # 教学班冲突：TCA 自身同时段再排一间教室
            r = c.post(f"{BASE}/teaching-schedules",
                       json=dict(base, teaching_class_id=env["tc_a"],
                                 classroom_id=env["room3"]), headers=admin)
            check(r.status_code == 409 and "CLASS" in r.json().get("code", ""),
                  "教学班冲突 → 409 CLASS_CONFLICT",
                  f"{r.status_code} {r.json().get('code')}")
            check(count_schedules(env["tc_a"]) == 1, "MySQL：教学班冲突未产生多余排课")

            # 修改同样检测冲突：给 TCA 再排一节（空闲时段），再改到与第一节重叠
            r2 = c.post(f"{BASE}/teaching-schedules",
                        json=dict(base, teaching_class_id=env["tc_a"],
                                  classroom_id=env["room3"], day_of_week=5,
                                  start_period=9, end_period=10), headers=admin)
            check(r2.status_code == 201, "空闲时段可再排一节", r2.text[:120])
            sid2 = r2.json()["id"]
            r = c.put(f"{BASE}/teaching-schedules/{sid2}",
                      json={"day_of_week": 3, "start_period": 5, "end_period": 6},
                      headers=admin)
            check(r.status_code == 409 and "CLASS" in r.json().get("code", ""),
                  "修改造成冲突 → 409 CLASS_CONFLICT",
                  f"{r.status_code} {r.json().get('code')}")
            with SessionLocal() as db:
                row2 = db.get(Schedule, sid2)
                check(row2.day_of_week == 5 and row2.start_period == 9,
                      "MySQL：冲突的修改未落库")
            r = c.delete(f"{BASE}/teaching-schedules/{sid2}", headers=admin)
            check(r.status_code == 204, "清理第二节排课")

            # ---------- Case D：权限 ----------
            print("\n[Case D] 数据权限")
            r = c.post(f"{BASE}/teaching-schedules",
                       json=dict(base, teaching_class_id=env["tc_b"],
                                 classroom_id=env["room3"]), headers=t1)
            check(r.status_code == 403, "教师新增排课 → 403", str(r.status_code))
            r = c.put(f"{BASE}/teaching-schedules/{sid}", json={"day_of_week": 5},
                      headers=t1)
            check(r.status_code == 403, "教师修改排课 → 403", str(r.status_code))
            r = c.delete(f"{BASE}/teaching-schedules/{sid}", headers=stu)
            check(r.status_code == 403, "学生删除排课 → 403", str(r.status_code))
            r = c.get(f"{BASE}/teaching-schedules", headers=t1)
            check(r.status_code == 403, "教师访问教务排课列表 → 403", str(r.status_code))

            # ---------- 教师 /mine ----------
            print("\n[教师课表] /teaching-schedules/mine")
            mine1 = c.get(f"{BASE}/teaching-schedules/mine",
                          params={"semester": SEM}, headers=t1).json()
            check({x["id"] for x in mine1} == {sid}, "教师甲只看到本人排课",
                  str([x["id"] for x in mine1]))
            mine2 = c.get(f"{BASE}/teaching-schedules/mine",
                          params={"semester": SEM}, headers=t2).json()
            check(mine2 == [], "教师乙看不到他人排课", str(mine2))
            # 周次过滤：第 3 周在 1-16 内，第 20 周不在
            inw = c.get(f"{BASE}/teaching-schedules/mine",
                        params={"semester": SEM, "week": 3}, headers=t1).json()
            outw = c.get(f"{BASE}/teaching-schedules/mine",
                         params={"semester": SEM, "week": 20}, headers=t1).json()
            check(len(inw) == 1 and outw == [], "周次过滤生效",
                  f"week3={len(inw)} week20={len(outw)}")
            other_sem = c.get(f"{BASE}/teaching-schedules/mine",
                              params={"semester": "2098-2098-1"}, headers=t1).json()
            check(other_sem == [], "按学期过滤：其它学期无数据", str(other_sem))

            # ---------- 学生 /my ----------
            print("\n[学生课表] /teaching-schedules/my")
            my = c.get(f"{BASE}/teaching-schedules/my",
                       params={"semester": SEM}, headers=stu).json()
            check({x["id"] for x in my} == {sid}, "学生只看到已选教学班的排课",
                  str([x["id"] for x in my]))
            check(all(x["course_name"] == "E2E7课程" for x in my),
                  "课表含课程名", str([x["course_name"] for x in my]))
            check(all(x["classroom_code"] for x in my), "课表含教室")
            check(all(x["teacher_name"] for x in my), "课表含教师")
            # 未选课程不可见：给 TCB（学生未选）排一节课
            r = c.post(f"{BASE}/teaching-schedules",
                       json=dict(base, teaching_class_id=env["tc_b"],
                                 classroom_id=env["room3"], day_of_week=4,
                                 start_period=7, end_period=8), headers=admin)
            check(r.status_code == 201, "为未选教学班排课成功", r.text[:120])
            my2 = c.get(f"{BASE}/teaching-schedules/my",
                        params={"semester": SEM}, headers=stu).json()
            check({x["id"] for x in my2} == {sid},
                  "学生课表仍不含未选课程的排课", str([x["id"] for x in my2]))

            # ---------- 删除 ----------
            print("\n[删除]")
            r = c.delete(f"{BASE}/teaching-schedules/{sid}", headers=admin)
            check(r.status_code == 204, "DELETE → 204")
            check(sched_row(sid) is None, "MySQL：排课已删除")
            after = c.get(f"{BASE}/teaching-schedules/mine",
                          params={"semester": SEM}, headers=t1).json()
            check(after == [], "教师课表同步移除已删排课", str(after))
    finally:
        cleanup()

    passed = sum(1 for ok, _ in results if ok)
    print(f"\n{'=' * 60}\n排课 HTTP+MySQL E2E：{passed}/{len(results)} 通过")
    for ok, label in results:
        if not ok:
            print(f"  ❌ {label}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
