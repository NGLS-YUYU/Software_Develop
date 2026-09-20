"""FIX-005：批量导入 + 成绩草稿删除测试。

覆盖（对应工单 §十七/§十八/§二十）：
- 教师批量导入（新增能力）：模板 / 导入 / 中文取值翻译 / 去重 / 权限
- 成绩模板按 AssessmentProfile 动态生成（32/48/64 × 实践/非实践）
- 真实 Excel 往返：下载模板 → 填写 → 上传 → 校验 MySQL 与总评（Case 1~3、7）
- 非法成绩 / 不存在的学生 / 不属于教学班的学生（Case 4~6）
- 成绩草稿删除：DRAFT 可删，SUBMITTED / APPROVED 拒绝（Case 8~10）
- 教师只能导入/删除本人授课教学班的成绩（对象级权限）
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.course import Course
from app.models.grade import Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import Schedule, TeachingClass, TeachingTask
from app.models.term import AcademicTerm
from app.models.user import User, UserType
from app.services.assessment import profile_for

client = TestClient(app)
PREFIX = settings.API_V1_PREFIX
LOGIN = f"{PREFIX}/auth/login"

P = "__f5__"
PWD = "f5test123"
SEMESTER = "2097-2097-1"  # 独立学期，避免与演示/其他测试数据冲突
XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def auth(username: str, password: str = PWD) -> dict:
    r = client.post(LOGIN, json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_auth() -> dict:
    return auth("admin", "admin123")


def _s(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _upload(path: str, data: bytes, headers: dict, filename="data.xlsx"):
    return client.post(
        path, files={"file": (filename, data, XLSX_CT)}, headers=headers
    )


def _download_template(kind: str, headers: dict, **params):
    r = client.get(f"{PREFIX}/imports/templates/{kind}", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def _headers_of(template: bytes) -> list[str]:
    ws = load_workbook(io.BytesIO(template)).worksheets[0]
    return [_s(c.value) for c in ws[1]]


def _fill(template: bytes, values_by_student_no: dict[str, dict[str, object]]) -> bytes:
    """打开系统生成的模板，按学号把成绩写进对应列（模拟教师真实操作）。"""
    wb = load_workbook(io.BytesIO(template))
    ws = wb.worksheets[0]
    headers = _headers_of(template)
    no_col = headers.index("学号") + 1
    for r in range(2, ws.max_row + 1):
        no = _s(ws.cell(r, no_col).value)
        for label, value in (values_by_student_no.get(no) or {}).items():
            ws.cell(r, headers.index(label) + 1).value = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _blank_workbook(headers: list[str], rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cleanup() -> None:
    with SessionLocal() as db:
        courses = select(Course.id).where(Course.code.like(f"{P}%"))
        tcs = select(TeachingClass.id).where(TeachingClass.code.like(f"{P}%"))
        students = select(Student.id).where(Student.student_no.like(f"{P}%"))
        db.execute(delete(Grade).where(or_(
            Grade.course_id.in_(courses),
            Grade.student_id.in_(students),
            Grade.teaching_class_id.in_(tcs),
        )))
        db.execute(delete(CourseSelection).where(or_(
            CourseSelection.teaching_class_id.in_(tcs),
            CourseSelection.student_id.in_(students),
        )))
        db.execute(delete(Schedule).where(Schedule.teaching_class_id.in_(tcs)))
        db.execute(delete(TeachingClass).where(TeachingClass.code.like(f"{P}%")))
        db.execute(delete(AcademicTerm).where(AcademicTerm.name.like(f"{P}%")))
        db.execute(delete(TeachingTask).where(TeachingTask.course_id.in_(courses)))
        db.execute(delete(Student).where(Student.student_no.like(f"{P}%")))
        db.execute(delete(Teacher).where(Teacher.teacher_no.like(f"{P}%")))
        db.execute(delete(User).where(User.username.like(f"{P}%")))
        db.execute(delete(Class).where(Class.code.like(f"{P}%")))
        db.execute(delete(Major).where(Major.code.like(f"{P}%")))
        db.execute(delete(Course).where(Course.code.like(f"{P}%")))
        db.execute(delete(College).where(College.code.like(f"{P}%")))
        db.commit()


@pytest.fixture
def env():
    """1 学院 / 1 专业 / 1 班 / 4 课程(32/32实践/48/64实践) / 2 教师 / 2 学生。

    s1 已选全部 4 个教学班；s2 未选任何教学班（用于「不属于该教学班」用例）。
    教学班 tc32/tc32p/tc48/tc64p 归教师甲；tc48b 归教师乙（用于越权用例）。
    """
    _cleanup()
    with SessionLocal() as db:
        college = College(code=f"{P}col", name="F5学院")
        db.add(college)
        db.flush()
        major = Major(code=f"{P}maj", name="F5专业", college_id=college.id)
        db.add(major)
        db.flush()
        klass = Class(code=f"{P}cls", name="F5一班", major_id=major.id, grade_year=2026)
        db.add(klass)
        db.flush()

        specs = [
            ("c32", "F5两段课", "2.0", 32, 32, 0),
            ("c32p", "F5两段实践课", "2.0", 32, 24, 8),
            ("c48", "F5三段课", "3.0", 48, 48, 0),
            ("c64p", "F5三段实践课", "4.0", 64, 48, 16),
        ]
        courses = {}
        for code, name, cr, total, theory, practice in specs:
            c = Course(
                code=f"{P}{code}", name=name, college_id=college.id,
                course_type="REQUIRED", credits=Decimal(cr),
                total_hours=total, theory_hours=theory, practice_hours=practice,
            )
            db.add(c)
            db.flush()
            courses[code] = c

        role_teacher = db.execute(
            select(Role).where(Role.code == RoleCode.TEACHER)
        ).scalar_one()
        role_student = db.execute(
            select(Role).where(Role.code == RoleCode.STUDENT)
        ).scalar_one()

        def make_user(username, real_name, user_type, role):
            u = User(
                username=username, password_hash=hash_password(PWD),
                real_name=real_name, user_type=user_type,
            )
            db.add(u)
            db.flush()
            db.add(UserRole(user_id=u.id, role_id=role.id))
            db.flush()
            return u

        ta_u = make_user(f"{P}t1", "教师甲", UserType.TEACHER, role_teacher)
        ta = Teacher(user_id=ta_u.id, teacher_no=f"{P}t1", college_id=college.id)
        tb_u = make_user(f"{P}t2", "教师乙", UserType.TEACHER, role_teacher)
        tb = Teacher(user_id=tb_u.id, teacher_no=f"{P}t2", college_id=college.id)
        db.add_all([ta, tb])
        db.flush()

        students = []
        for i in (1, 2):
            no = f"{P}s{i}"
            u = make_user(no, f"学生{i}", UserType.STUDENT, role_student)
            s = Student(
                user_id=u.id, student_no=no, class_id=klass.id,
                major_id=major.id, college_id=college.id, enrollment_year=2026,
            )
            db.add(s)
            db.flush()
            students.append(s)

        term = AcademicTerm(
            name=f"{P}term", academic_year="2101-2102", semester=1,
            start_date=date(2101, 9, 1), end_date=date(2102, 1, 15),
            status="PLANNED",
        )
        db.add(term)
        db.flush()

        # 教学任务：(semester, course_id, college_id) 唯一，同一课程只建一个任务
        tasks = {}
        for code, course in courses.items():
            task = TeachingTask(
                semester=SEMESTER, course_id=course.id, college_id=college.id,
                status="CONFIRMED", planned_classes=2,
            )
            db.add(task)
            db.flush()
            tasks[code] = task

        def make_tc(code, course_code, teacher):
            tc = TeachingClass(
                code=f"{P}{code}", task_id=tasks[course_code].id,
                course_id=courses[course_code].id,
                semester=SEMESTER, teacher_id=teacher.id, capacity=60,
                term_id=term.id,
            )
            db.add(tc)
            db.flush()
            return tc

        tc32 = make_tc("tc32", "c32", ta)
        tc32p = make_tc("tc32p", "c32p", ta)
        tc48 = make_tc("tc48", "c48", ta)
        tc64p = make_tc("tc64p", "c64p", ta)
        tc48b = make_tc("tc48b", "c48", tb)

        # s1 选全部 4 个教学班；tc48b 无人选（越权用例只用到 s1 的越权尝试）
        for tc in (tc32, tc32p, tc48, tc64p):
            db.add(CourseSelection(
                student_id=students[0].id, teaching_class_id=tc.id,
                course_id=tc.course_id, semester=SEMESTER,
                status=SelectionState.SELECTED,
            ))
        db.add(CourseSelection(
            student_id=students[0].id, teaching_class_id=tc48b.id,
            course_id=tc48b.course_id, semester=SEMESTER,
            status=SelectionState.SELECTED,
        ))
        db.commit()

        yield {
            "college_name": college.name,
            "ta_uname": f"{P}t1", "tb_uname": f"{P}t2",
            "s1_uname": f"{P}s1", "s1_no": students[0].student_no,
            "s2_no": students[1].student_no, "s1_id": students[0].id,
            "tc32": tc32.id, "tc32p": tc32p.id, "tc48": tc48.id, "tc64p": tc64p.id,
            "tc48b": tc48b.id,
            "tc32_code": tc32.code, "tc32p_code": tc32p.code,
            "tc48_code": tc48.code, "tc64p_code": tc64p.code,
            "tc48b_code": tc48b.code,
            "ta_id": ta.id,
        }
    _cleanup()


def _grade(tc_id: int, student_id: int) -> Grade | None:
    with SessionLocal() as db:
        return db.execute(
            select(Grade).where(
                Grade.teaching_class_id == tc_id, Grade.student_id == student_id
            )
        ).scalar_one_or_none()


# =========================== 教师批量导入 ===========================


def test_teacher_template_fields(env):
    content = _download_template("teachers", admin_auth())
    headers = _headers_of(content)
    assert headers[:3] == ["工号", "姓名", "学院"]
    assert "职称" in headers and "性别" in headers


def test_admin_can_import_teachers(env):
    data = _blank_workbook(
        ["工号", "姓名", "学院", "职称", "性别", "联系电话"],
        [
            [f"{P}new1", "王教授", "F5学院", "教授", "男", "13800000001"],
            [f"{P}new2", "李讲师", "F5学院", "讲师", "女", "13800000002"],
        ],
    )
    r = _upload(f"{PREFIX}/imports/teachers", data, admin_auth())
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 2 and r.json()["failed"] == 0
    with SessionLocal() as db:
        t = db.execute(
            select(Teacher).where(Teacher.teacher_no == f"{P}new1")
        ).scalar_one()
        assert t.title == "PROFESSOR" and t.gender == "MALE"
        assert t.user.real_name == "王教授"
        assert t.user.phone == "13800000001"
        # 初始密码 = 工号，可直接登录（与学生/教师服务一致）
    r2 = client.post(LOGIN, json={"username": f"{P}new1", "password": f"{P}new1"})
    assert r2.status_code == 200


def test_teacher_import_duplicate_and_unknown_college(env):
    data = _blank_workbook(
        ["工号", "姓名", "学院"],
        [
            [f"{P}t1", "重复工号", "F5学院"],
            [f"{P}new3", "无院教师", "不存在的学院"],
            [f"{P}new3", "文件内重复", "F5学院"],
            [f"{P}new3", "文件内重复2", "F5学院"],
        ],
    )
    r = _upload(f"{PREFIX}/imports/teachers", data, admin_auth())
    assert r.json()["success"] == 1 and r.json()["failed"] == 3
    msgs = [e["message"] for e in r.json()["errors"]]
    assert any("工号已存在" in m for m in msgs)
    assert any("学院不存在" in m for m in msgs)
    assert any("在导入文件中重复" in m for m in msgs)


def test_teacher_import_invalid_title(env):
    data = _blank_workbook(
        ["工号", "姓名", "学院", "职称"],
        [[f"{P}new4", "错职称", "F5学院", "院士"]],
    )
    r = _upload(f"{PREFIX}/imports/teachers", data, admin_auth())
    assert r.json()["failed"] == 1
    assert "职称非法" in r.json()["errors"][0]["message"]


def test_only_admin_can_import_teachers(env):
    data = _blank_workbook(
        ["工号", "姓名", "学院"], [[f"{P}new5", "越权", "F5学院"]]
    )
    assert _upload(
        f"{PREFIX}/imports/teachers", data, auth(env["ta_uname"])
    ).status_code == 403
    assert _upload(
        f"{PREFIX}/imports/teachers", data, auth(env["s1_uname"])
    ).status_code == 403


# =========================== 成绩模板动态列 ===========================


@pytest.mark.parametrize(
    "tc_key,expected,absent",
    [
        ("tc32", ["平时成绩", "期末成绩"],
         ["期中成绩", "期中实践", "期末实践"]),
        ("tc32p", ["平时成绩", "期末理论", "期末实践"],
         ["期中成绩", "期中理论", "期中实践"]),
        ("tc48", ["平时成绩", "期中成绩", "期末成绩"],
         ["期中实践", "期末实践"]),
        ("tc64p", ["平时成绩", "期中理论", "期中实践", "期末理论", "期末实践"], []),
    ],
)
def test_grade_template_columns_follow_assessment_profile(env, tc_key, expected, absent):
    """FIX-005 §七：模板列由后端 AssessmentProfile 决定，前端不写 32/48/64 判断。"""
    content = _download_template(
        "grades", auth(env["ta_uname"]), teaching_class_id=env[tc_key]
    )
    headers = _headers_of(content)
    for label in ["学号", "姓名", "班级", "课程代码", "课程名称", "教学班"]:
        assert label in headers, f"缺少固定列 {label}"
    for label in expected:
        assert label in headers, f"{tc_key} 应包含 {label}：{headers}"
    for label in absent:
        assert label not in headers, f"{tc_key} 不应包含 {label}：{headers}"


def test_grade_template_contains_roster(env):
    """教师无需填写学号/姓名：模板已带出教学班学生名单。"""
    content = _download_template(
        "grades", auth(env["ta_uname"]), teaching_class_id=env["tc48"]
    )
    ws = load_workbook(io.BytesIO(content)).worksheets[0]
    headers = _headers_of(content)
    no_col = headers.index("学号") + 1
    rows = [_s(ws.cell(r, no_col).value) for r in range(2, ws.max_row + 1)]
    assert rows == [env["s1_no"]]
    assert _s(ws.cell(2, headers.index("姓名") + 1).value) == "学生1"
    assert _s(ws.cell(2, headers.index("教学班") + 1).value) == env["tc48_code"]


def test_grade_template_unknown_class(env):
    r = client.get(
        f"{PREFIX}/imports/templates/grades",
        params={"teaching_class_id": 99999999},
        headers=auth(env["ta_uname"]),
    )
    assert r.status_code == 404


# =========================== 真实 Excel 往返（Case 1~3、7） ===========================


def test_case1_32h_roundtrip(env):
    """32h 无实践：平时 + 期末 → 草稿 + 总评 80*0.2+90*0.8=88.00。"""
    tpl = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc32"])
    data = _fill(tpl, {env["s1_no"]: {"平时成绩": 80, "期末成绩": 90}})
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.status_code == 200, r.text
    assert r.json()["success"] == 1 and r.json()["failed"] == 0
    g = _grade(env["tc32"], env["s1_id"])
    assert g.status == GradeStatus.DRAFT
    assert g.total_score == Decimal("88.00")
    assert g.practice_total_score is None


def test_case2_48h_roundtrip(env):
    """48h 无实践：平时 + 期中 + 期末 → 80*0.2+70*0.3+90*0.5=82.00。"""
    tpl = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc48"])
    data = _fill(tpl, {env["s1_no"]: {"平时成绩": 80, "期中成绩": 70, "期末成绩": 90}})
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["success"] == 1
    g = _grade(env["tc48"], env["s1_id"])
    assert g.total_score == Decimal("82.00")
    assert g.theory_total_score == Decimal("82.00")


def test_case3_64h_practice_roundtrip(env):
    """64h + 实践：理论与实践分别录入，两侧平均。"""
    tpl = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc64p"])
    data = _fill(tpl, {env["s1_no"]: {
        "平时成绩": 80, "期中理论": 80, "期中实践": 90,
        "期末理论": 70, "期末实践": 90,
    }})
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["success"] == 1
    g = _grade(env["tc64p"], env["s1_id"])
    # 理论 80*.2+80*.3+70*.5=75.00；实践 80*.2+90*.3+90*.5=88.00 → 81.50
    assert g.theory_total_score == Decimal("75.00")
    assert g.practice_total_score == Decimal("88.00")
    assert g.total_score == Decimal("81.50")
    assert g.mid_score == Decimal("85.00") and g.final_score == Decimal("80.00")


def test_case3b_32h_practice_roundtrip(env):
    """32h + 实践：无期中，期末理论与期末实践成对。"""
    tpl = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc32p"])
    data = _fill(tpl, {env["s1_no"]: {
        "平时成绩": 80, "期末理论": 70, "期末实践": 90,
    }})
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["success"] == 1
    g = _grade(env["tc32p"], env["s1_id"])
    # 理论 80*.2+70*.8=72；实践 80*.2+90*.8=88 → 80.00
    assert g.total_score == Decimal("80.00")


def test_case7_reimport_same_template_is_draft_overwrite(env):
    """Case 7 重复导入：模板回填草稿，再次导入覆盖草稿而不报错。"""
    tpl = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc48"])
    first = _fill(tpl, {env["s1_no"]: {"平时成绩": 80, "期中成绩": 70, "期末成绩": 90}})
    assert _upload(f"{PREFIX}/imports/grades", first, auth(env["ta_uname"])).json()["success"] == 1

    tpl2 = _download_template("grades", auth(env["ta_uname"]), teaching_class_id=env["tc48"])
    ws = load_workbook(io.BytesIO(tpl2)).worksheets[0]
    headers = _headers_of(tpl2)
    assert _s(ws.cell(2, headers.index("平时成绩") + 1).value) == "80"  # 已回填
    second = _fill(tpl2, {env["s1_no"]: {"平时成绩": 95}})
    r = _upload(f"{PREFIX}/imports/grades", second, auth(env["ta_uname"]))
    assert r.json()["success"] == 1
    g = _grade(env["tc48"], env["s1_id"])
    assert g.regular_score == Decimal("95.00")
    assert g.status == GradeStatus.DRAFT


def test_dynamic_template_rejects_merged_column_on_practice_course(env):
    """实践课模板不给「期中成绩」列：强行按合并列导入 → 行级报错。"""
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[env["s1_no"], env["tc64p_code"], 80, 70, 90]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["failed"] == 1
    assert "必须分别导入理论/实践成绩" in r.json()["errors"][0]["message"]


# =========================== 错误处理（Case 4~6） ===========================


def test_case4_invalid_scores(env):
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [
            [env["s1_no"], env["tc48_code"], -1, 70, 90],
            [env["s1_no"], env["tc48_code"], 80, 101, 90],
            [env["s1_no"], env["tc48_code"], 80, 70, "缺考"],
        ],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["failed"] == 3
    msgs = " ".join(e["message"] for e in r.json()["errors"])
    assert "超出范围" in msgs and "非法数字" in msgs
    assert _grade(env["tc48"], env["s1_id"]) is None  # 全部拒绝，不产生脏数据


def test_case4b_empty_score_saved_as_incomplete_draft(env):
    """空值不是错误：保留为不完整草稿，总评留空（提交时才拦截）。"""
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[env["s1_no"], env["tc48_code"], 80, "", ""]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["success"] == 1
    g = _grade(env["tc48"], env["s1_id"])
    assert g.status == GradeStatus.DRAFT and g.total_score is None


def test_case5_student_not_exist(env):
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[f"{P}nosuch", env["tc48_code"], 80, 70, 90]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["failed"] == 1
    assert "学生不存在" in r.json()["errors"][0]["message"]


def test_case6_student_not_in_class(env):
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[env["s2_no"], env["tc48_code"], 80, 70, 90]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["failed"] == 1
    assert "学生不属于该教学班" in r.json()["errors"][0]["message"]


def test_error_reports_row_number(env):
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [
            [env["s1_no"], env["tc48_code"], 80, 70, 90],
            [env["s1_no"], env["tc48_code"], 80, 70, 999],
        ],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["total"] == 2 and r.json()["success"] == 1 and r.json()["failed"] == 1
    err = r.json()["errors"][0]
    assert err["row"] == 3 and err["field"] == "final_score"
    assert "超出范围" in err["message"]


# =========================== 对象级权限 ===========================


def test_teacher_cannot_import_into_other_teacher_class(env):
    """教师乙的教学班：教师甲导入该行被拒（CLAUDE.md §9 对象级校验）。"""
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[env["s1_no"], env["tc48b_code"], 80, 70, 90]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, auth(env["ta_uname"]))
    assert r.json()["failed"] == 1
    assert "只能导入本人授课教学班" in r.json()["errors"][0]["message"]
    assert _grade(env["tc48b"], env["s1_id"]) is None

    # 教师乙本人导入同一行 → 成功
    r2 = _upload(f"{PREFIX}/imports/grades", data, auth(env["tb_uname"]))
    assert r2.json()["success"] == 1
    assert _grade(env["tc48b"], env["s1_id"]) is not None


def test_admin_can_import_any_class(env):
    data = _blank_workbook(
        ["学号", "教学班", "平时成绩", "期中成绩", "期末成绩"],
        [[env["s1_no"], env["tc48b_code"], 80, 70, 90]],
    )
    assert _upload(f"{PREFIX}/imports/grades", data, admin_auth()).json()["success"] == 1


# =========================== 成绩草稿删除（Case 8~10） ===========================


def _make_grade(tc_id: int, student_id: int, status: str) -> int:
    with SessionLocal() as db:
        tc = db.get(TeachingClass, tc_id)
        g = Grade(
            student_id=student_id, teaching_class_id=tc_id, course_id=tc.course_id,
            semester=tc.semester, credits=Decimal("3.0"),
            regular_score=Decimal("50.00"), status=status,
        )
        db.add(g)
        db.commit()
        return g.id


def test_case8_delete_draft(env):
    gid = _make_grade(env["tc48"], env["s1_id"], GradeStatus.DRAFT)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["ta_uname"]))
    assert r.status_code == 204, r.text
    assert _grade(env["tc48"], env["s1_id"]) is None
    # 删除后名单回到「未录入」
    roster = client.get(
        f"{PREFIX}/grades/teaching-classes/{env['tc48']}/students",
        headers=auth(env["ta_uname"]),
    ).json()
    assert roster[0]["entry_status"] == "NOT_ENTERED"


def test_case9_cannot_delete_submitted(env):
    gid = _make_grade(env["tc48"], env["s1_id"], GradeStatus.SUBMITTED)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["ta_uname"]))
    assert r.status_code == 409
    assert "只有草稿可以删除" in r.json()["message"]
    assert _grade(env["tc48"], env["s1_id"]) is not None  # 未被删除


def test_case10_cannot_delete_approved(env):
    gid = _make_grade(env["tc48"], env["s1_id"], GradeStatus.APPROVED)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["ta_uname"]))
    assert r.status_code == 409
    assert _grade(env["tc48"], env["s1_id"]) is not None


def test_cannot_delete_rejected(env):
    gid = _make_grade(env["tc48"], env["s1_id"], GradeStatus.REJECTED)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["ta_uname"]))
    assert r.status_code == 409


def test_teacher_cannot_delete_other_teacher_draft(env):
    gid = _make_grade(env["tc48b"], env["s1_id"], GradeStatus.DRAFT)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["ta_uname"]))
    assert r.status_code == 403
    assert _grade(env["tc48b"], env["s1_id"]) is not None


def test_student_cannot_delete_grade(env):
    gid = _make_grade(env["tc48"], env["s1_id"], GradeStatus.DRAFT)
    r = client.delete(f"{PREFIX}/grades/{gid}", headers=auth(env["s1_uname"]))
    assert r.status_code == 403


def test_admin_can_delete_draft(env):
    gid = _make_grade(env["tc48b"], env["s1_id"], GradeStatus.DRAFT)
    assert client.delete(
        f"{PREFIX}/grades/{gid}", headers=admin_auth()
    ).status_code == 204


def test_delete_missing_grade(env):
    r = client.delete(f"{PREFIX}/grades/99999999", headers=auth(env["ta_uname"]))
    assert r.status_code == 404


# =========================== 模板结构（说明页 / 中文表头兼容） ===========================


def test_templates_have_notes_sheet(env):
    for kind in ("students", "teachers", "courses"):
        wb = load_workbook(io.BytesIO(_download_template(kind, admin_auth())))
        assert wb.sheetnames == ["导入模板", "填写说明"], kind
        assert wb["填写说明"].max_row >= 3


def test_english_headers_still_accepted(env):
    """兼容既有英文表头模板（不得打断已有调用方）。"""
    data = _blank_workbook(
        ["student_no", "teaching_class_code", "regular_score", "mid_score", "final_score"],
        [[env["s1_no"], env["tc48_code"], 80, 70, 90]],
    )
    r = _upload(f"{PREFIX}/imports/grades", data, admin_auth())
    assert r.json()["success"] == 1
    assert _grade(env["tc48"], env["s1_id"]).total_score == Decimal("82.00")


def test_profile_of_fixture_courses(env):
    """固定装置自检：4 门课程的考核结构符合用例假设。"""
    with SessionLocal() as db:
        c32p = db.execute(
            select(Course).where(Course.code == f"{P}c32p")
        ).scalar_one()
        p = profile_for(c32p)
        assert p.assessment_type == "32" and p.has_midterm is False
        assert p.has_practice is True
