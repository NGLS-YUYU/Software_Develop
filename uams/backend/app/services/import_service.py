"""Excel 批量导入业务逻辑（TASK-010）。

架构约束（CLAUDE.md §22 / V2.0 指南）：
  - 学生导入：ImportService → StudentService（复用用户/学生创建 + RBAC）
  - 课程导入：ImportService → CourseService
  - 成绩导入：ImportService → GradeService → ScoreService（禁止自行计算成绩）
  - 禁止跨层直接操作数据库；不自动创建学院/专业/班级/教学班/教师/选课
  - 成绩导入一律保存为 DRAFT，不写 GPA / 排名
"""

from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.models.course import Course, CourseType
from app.models.grade import PASS_SCORE, Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.models.user import User
from app.services.course import CourseService
from app.services.grade import GradeService
from app.services.person import StudentService

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- 模板字段定义（与 V2.0 指南一致） ---
_STUDENT_HEADERS = ["student_no", "name", "username", "college", "major", "class_name"]
_COURSE_HEADERS = [
    "course_code", "course_name", "college", "credits", "total_hours",
    "theory_hours", "practice_hours", "course_type",
]
_GRADE_HEADERS = [
    "student_no", "teaching_class_code",
    "regular_score", "mid_score", "final_score",
    "mid_theory_score", "mid_practice_score",
    "final_theory_score", "final_practice_score",
    "theory_makeup_score", "practice_makeup_score",
]
_GRADE_SCORE_FIELDS = [
    "regular_score", "mid_score", "final_score",
    "mid_theory_score", "mid_practice_score",
    "final_theory_score", "final_practice_score",
    "theory_makeup_score", "practice_makeup_score",
]
_SCORE_LABELS = {
    "regular_score": "平时成绩",
    "mid_score": "期中成绩",
    "final_score": "期末成绩",
    "mid_theory_score": "期中理论成绩",
    "mid_practice_score": "期中实践成绩",
    "final_theory_score": "期末理论成绩",
    "final_practice_score": "期末实践成绩",
    "theory_makeup_score": "理论补考成绩",
    "practice_makeup_score": "实践补考成绩",
}


def _cell_str(value) -> str:
    """把 Excel 单元格值规范化为字符串。

    处理常见坑：数字被 Excel 存成 float（20230001 → 20230001.0），
    这里对整数值去掉 .0；文本型学号（如 00123）原样保留。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _cell_decimal(value) -> Decimal | None:
    """把 Excel 单元格值解析为 Decimal；空值/NaN 返回 None，非法值抛 ValueError。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    if isinstance(value, float) and not Decimal(str(value)).is_finite():
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"非法数字：{value}") from e


def _load_sheet(file_bytes: bytes):
    """校验文件大小与格式，返回首个工作表。"""
    if not file_bytes:
        raise Conflict("文件内容为空")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise Conflict(f"文件过大（超过 {MAX_FILE_SIZE // (1024 * 1024)}MB）")
    try:
        wb = load_workbook(BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise Conflict("文件格式错误：仅支持 .xlsx 格式") from e
    if not wb.sheetnames:
        raise Conflict("Excel 文件为空")
    return wb[wb.sheetnames[0]]


def _header_map(ws) -> dict[str, int]:
    hmap: dict[str, int] = {}
    for idx in range(1, ws.max_column + 1):
        key = _cell_str(ws.cell(row=1, column=idx).value)
        if key:
            hmap[key] = idx
    return hmap


def _require_headers(hmap: dict[str, int], required: list[str]) -> None:
    missing = [h for h in required if h not in hmap]
    if missing:
        raise Conflict(f"模板缺少必要字段：{', '.join(missing)}")


def _load_refs(db: Session, model, values: set[str]) -> tuple[dict, dict]:
    """按 code / name 批量加载组织对象，返回 (code_map, name_map)。"""
    code_map: dict[str, object] = {}
    name_map: dict[str, object] = {}
    values = {v for v in values if v}
    if not values:
        return code_map, name_map
    rows = db.execute(
        select(model).where(
            or_(model.code.in_(values), model.name.in_(values))
        )
    ).scalars()
    for obj in rows:
        code_map[obj.code] = obj
        name_map[obj.name] = obj
    return code_map, name_map


def _lookup(refs: tuple[dict, dict], value: str):
    code_map, name_map = refs
    return code_map.get(value) or name_map.get(value)


def _template_bytes(headers: list[str], example: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "导入模板"
    ws.append(headers)
    ws.append(example)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ImportService:
    """Excel 批量导入。"""

    def __init__(self, db: Session):
        self.db = db

    # =========================== 模板下载 ===========================

    def student_template(self) -> bytes:
        return _template_bytes(
            _STUDENT_HEADERS,
            ["20240001", "张三", "20240001", "信息工程学院", "软件工程", "软件2401班"],
        )

    def course_template(self) -> bytes:
        return _template_bytes(
            _COURSE_HEADERS,
            ["CS101", "程序设计基础", "信息工程学院", 4.0, 64, 40, 24, "REQUIRED"],
        )

    def grade_template(self) -> bytes:
        return _template_bytes(
            _GRADE_HEADERS,
            ["20240001", "CS101-01", 85, 80, 90, "", "", "", "", "", ""],
        )

    # =========================== 学生导入 ===========================

    def import_students(self, file_bytes: bytes) -> dict:
        ws = _load_sheet(file_bytes)
        hmap = _header_map(ws)
        _require_headers(hmap, _STUDENT_HEADERS)

        rows: list[dict] = []
        college_vals: set[str] = set()
        major_vals: set[str] = set()
        class_vals: set[str] = set()
        no_vals: set[str] = set()
        username_vals: set[str] = set()
        for r in range(2, ws.max_row + 1):
            student_no = _cell_str(ws.cell(r, hmap["student_no"]).value)
            name = _cell_str(ws.cell(r, hmap["name"]).value)
            username = _cell_str(ws.cell(r, hmap["username"]).value) or student_no
            college_v = _cell_str(ws.cell(r, hmap["college"]).value)
            major_v = _cell_str(ws.cell(r, hmap["major"]).value)
            class_v = _cell_str(ws.cell(r, hmap["class_name"]).value)
            if not any([student_no, name, username, college_v, major_v, class_v]):
                continue  # 空行
            rows.append(
                {
                    "row": r, "student_no": student_no, "name": name,
                    "username": username, "college": college_v,
                    "major": major_v, "class_name": class_v,
                }
            )
            college_vals.add(college_v)
            major_vals.add(major_v)
            class_vals.add(class_v)
            no_vals.add(student_no)
            username_vals.add(username)

        colleges = _load_refs(self.db, College, college_vals)
        majors = _load_refs(self.db, Major, major_vals)
        classes = _load_refs(self.db, Class, class_vals)
        existing_nos = set(
            self.db.execute(
                select(Student.student_no).where(Student.student_no.in_(no_vals))
            ).scalars()
        )
        existing_usernames = set(
            self.db.execute(
                select(User.username).where(User.username.in_(username_vals))
            ).scalars()
        )

        svc = StudentService(self.db)
        errors: list[dict] = []
        seen_nos: set[str] = set()
        seen_usernames: set[str] = set()
        success = 0
        for row in rows:
            r = row["row"]

            def fail(field: str, msg: str) -> dict:
                return {"row": r, "field": field, "message": msg}

            if not row["student_no"]:
                errors.append(fail("student_no", "学号不能为空")); continue
            if not row["name"]:
                errors.append(fail("name", "姓名不能为空")); continue
            if not row["username"]:
                errors.append(fail("username", "登录名不能为空")); continue
            if not row["college"]:
                errors.append(fail("college", "学院不能为空")); continue
            if not row["major"]:
                errors.append(fail("major", "专业不能为空")); continue
            if not row["class_name"]:
                errors.append(fail("class_name", "行政班不能为空")); continue

            college = _lookup(colleges, row["college"])
            if college is None:
                errors.append(fail("college", f"学院不存在：{row['college']}")); continue
            major = _lookup(majors, row["major"])
            if major is None:
                errors.append(fail("major", f"专业不存在：{row['major']}")); continue
            if major.college_id != college.id:
                errors.append(fail("major", "专业与学院不匹配")); continue
            klass = _lookup(classes, row["class_name"])
            if klass is None:
                errors.append(fail("class_name", f"行政班不存在：{row['class_name']}")); continue
            if klass.major_id != major.id:
                errors.append(fail("class_name", "行政班与专业不匹配")); continue

            if row["student_no"] in existing_nos:
                errors.append(fail("student_no", f"学号已存在：{row['student_no']}")); continue
            if row["student_no"] in seen_nos:
                errors.append(fail("student_no", f"学号在导入文件中重复：{row['student_no']}")); continue
            if row["username"] in existing_usernames:
                errors.append(fail("username", f"登录名已存在：{row['username']}")); continue
            if row["username"] in seen_usernames:
                errors.append(fail("username", f"登录名在导入文件中重复：{row['username']}")); continue

            seen_nos.add(row["student_no"])
            seen_usernames.add(row["username"])
            svc.create_student(
                {
                    "student_no": row["student_no"],
                    "real_name": row["name"],
                    "username": row["username"],
                    "class_id": klass.id,
                    # 入学年份与行政班 grade_year 保持一致
                    "enrollment_year": klass.grade_year,
                }
            )
            success += 1

        return {
            "total": len(rows),
            "success": success,
            "failed": len(errors),
            "errors": errors,
        }

    # =========================== 课程导入 ===========================

    def import_courses(self, file_bytes: bytes) -> dict:
        ws = _load_sheet(file_bytes)
        hmap = _header_map(ws)
        _require_headers(hmap, _COURSE_HEADERS)

        rows: list[dict] = []
        college_vals: set[str] = set()
        code_vals: set[str] = set()
        for r in range(2, ws.max_row + 1):
            course_code = _cell_str(ws.cell(r, hmap["course_code"]).value)
            course_name = _cell_str(ws.cell(r, hmap["course_name"]).value)
            college_v = _cell_str(ws.cell(r, hmap["college"]).value)
            credits_raw = ws.cell(r, hmap["credits"]).value
            hours_raw = ws.cell(r, hmap["total_hours"]).value
            theory_raw = ws.cell(r, hmap["theory_hours"]).value
            practice_raw = ws.cell(r, hmap["practice_hours"]).value
            ctype = _cell_str(ws.cell(r, hmap["course_type"]).value)
            if not any([course_code, course_name, college_v,
                        _cell_str(credits_raw), _cell_str(hours_raw),
                        _cell_str(theory_raw), _cell_str(practice_raw), ctype]):
                continue
            rows.append(
                {
                    "row": r, "course_code": course_code, "course_name": course_name,
                    "college": college_v, "credits_raw": credits_raw,
                    "hours_raw": hours_raw, "theory_raw": theory_raw,
                    "practice_raw": practice_raw, "course_type": ctype,
                }
            )
            college_vals.add(college_v)
            code_vals.add(course_code)

        colleges = _load_refs(self.db, College, college_vals)
        existing_codes = set(
            self.db.execute(
                select(Course.code).where(Course.code.in_(code_vals))
            ).scalars()
        )

        svc = CourseService(self.db)
        errors: list[dict] = []
        seen: set[str] = set()
        success = 0
        for row in rows:
            r = row["row"]

            def fail(field: str, msg: str) -> dict:
                return {"row": r, "field": field, "message": msg}

            if not row["course_code"]:
                errors.append(fail("course_code", "课程编号不能为空")); continue
            if not row["course_name"]:
                errors.append(fail("course_name", "课程名称不能为空")); continue
            if not row["college"]:
                errors.append(fail("college", "学院不能为空")); continue
            college = _lookup(colleges, row["college"])
            if college is None:
                errors.append(fail("college", f"学院不存在：{row['college']}")); continue

            try:
                credits = _cell_decimal(row["credits_raw"])
            except ValueError as e:
                errors.append(fail("credits", str(e))); continue
            if credits is None:
                errors.append(fail("credits", "学分不能为空")); continue
            if not (Decimal("0") < credits <= Decimal("30")):
                errors.append(fail("credits", "学分必须大于 0")); continue

            try:
                hours = _cell_decimal(row["hours_raw"])
            except ValueError as e:
                errors.append(fail("total_hours", str(e))); continue
            if hours is None:
                errors.append(fail("total_hours", "学时不能为空")); continue
            if not (Decimal("0") <= hours <= Decimal("500")):
                errors.append(fail("total_hours", "学时必须在 0-500 之间")); continue
            if hours != int(hours):
                errors.append(fail("total_hours", "学时必须是整数")); continue

            try:
                theory = _cell_decimal(row["theory_raw"])
            except ValueError as e:
                errors.append(fail("theory_hours", str(e))); continue
            try:
                practice = _cell_decimal(row["practice_raw"])
            except ValueError as e:
                errors.append(fail("practice_hours", str(e))); continue
            theory = int(theory) if theory is not None else 0
            practice = int(practice) if practice is not None else 0
            if not (Decimal("0") <= Decimal(theory) <= Decimal("500")
                    and Decimal("0") <= Decimal(practice) <= Decimal("500")):
                errors.append(fail("theory_hours", "学时必须在 0-500 之间")); continue
            if theory + practice != int(hours):
                errors.append(fail(
                    "theory_hours",
                    f"理论课时 + 实践课时必须等于总学时（{int(hours)}）。"
                    f"当前：理论 {theory} + 实践 {practice} = {theory + practice}。"
                )); continue

            if row["course_type"] not in CourseType.ALL:
                errors.append(fail("course_type", f"课程类型非法：{row['course_type']}")); continue

            if row["course_code"] in existing_codes:
                errors.append(fail("course_code", f"课程编号已存在：{row['course_code']}")); continue
            if row["course_code"] in seen:
                errors.append(fail("course_code", f"课程编号在导入文件中重复：{row['course_code']}")); continue

            seen.add(row["course_code"])
            svc.create(
                {
                    "code": row["course_code"],
                    "name": row["course_name"],
                    "college_id": college.id,
                    "course_type": row["course_type"],
                    "credits": credits,
                    "total_hours": int(hours),
                    "theory_hours": theory,
                    "practice_hours": practice,
                }
            )
            success += 1

        return {
            "total": len(rows),
            "success": success,
            "failed": len(errors),
            "errors": errors,
        }

    # =========================== 成绩导入 ===========================

    def import_grades(self, file_bytes: bytes) -> dict:
        ws = _load_sheet(file_bytes)
        hmap = _header_map(ws)
        _require_headers(hmap, _GRADE_HEADERS)

        rows: list[dict] = []
        student_nos: set[str] = set()
        tc_codes: set[str] = set()
        for r in range(2, ws.max_row + 1):
            student_no = _cell_str(ws.cell(r, hmap["student_no"]).value)
            tc_code = _cell_str(ws.cell(r, hmap["teaching_class_code"]).value)
            scores_raw = {
                f: ws.cell(r, hmap[f]).value for f in _GRADE_SCORE_FIELDS
            }
            if (
                not student_no and not tc_code
                and all(_cell_str(v) == "" for v in scores_raw.values())
            ):
                continue
            rows.append(
                {
                    "row": r, "student_no": student_no,
                    "teaching_class_code": tc_code, "scores_raw": scores_raw,
                }
            )
            if student_no:
                student_nos.add(student_no)
            if tc_code:
                tc_codes.add(tc_code)

        students_by_no = {
            s.student_no: s
            for s in self.db.execute(
                select(Student).where(Student.student_no.in_(student_nos))
            ).scalars()
        }
        tcs_by_code = {
            t.code: t
            for t in self.db.execute(
                select(TeachingClass).where(TeachingClass.code.in_(tc_codes))
            ).scalars()
        }
        courses_by_id = {
            c.id: c
            for c in self.db.execute(
                select(Course).where(
                    Course.id.in_([t.course_id for t in tcs_by_code.values()])
                )
            ).scalars()
        }
        involved_student_ids = {s.id for s in students_by_no.values()}
        involved_tc_ids = {t.id for t in tcs_by_code.values()}

        grades_by_key = {
            (g.student_id, g.teaching_class_id): g
            for g in self.db.execute(
                select(Grade).where(
                    Grade.student_id.in_(involved_student_ids),
                    Grade.teaching_class_id.in_(involved_tc_ids),
                )
            ).scalars()
        }
        selection_keys = set(
            self.db.execute(
                select(CourseSelection.student_id, CourseSelection.teaching_class_id)
                .where(
                    CourseSelection.student_id.in_(involved_student_ids),
                    CourseSelection.teaching_class_id.in_(involved_tc_ids),
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).all()
        )

        errors: list[dict] = []
        valid_rows: list[dict] = []
        for row in rows:
            r = row["row"]

            def fail(field: str, msg: str) -> dict:
                return {"row": r, "field": field, "message": msg}

            if not row["student_no"]:
                errors.append(fail("student_no", "学号不能为空")); continue
            student = students_by_no.get(row["student_no"])
            if student is None:
                errors.append(fail("student_no", f"学生不存在：{row['student_no']}")); continue
            if not row["teaching_class_code"]:
                errors.append(fail("teaching_class_code", "教学班编号不能为空")); continue
            tc = tcs_by_code.get(row["teaching_class_code"])
            if tc is None:
                errors.append(fail("teaching_class_code", f"教学班不存在：{row['teaching_class_code']}")); continue

            key = (student.id, tc.id)
            grade = grades_by_key.get(key)
            if grade is None and key not in selection_keys:
                errors.append(fail("teaching_class_code", "学生不属于该教学班")); continue
            if grade is not None and grade.status == GradeStatus.SUBMITTED:
                errors.append(fail("teaching_class_code", "成绩已提交待审核，不能覆盖")); continue
            if grade is not None and grade.status == GradeStatus.APPROVED:
                errors.append(fail("teaching_class_code", "成绩已审核通过，不能覆盖")); continue

            scores: dict[str, Decimal] = {}
            score_err = None
            for f in _GRADE_SCORE_FIELDS:
                try:
                    d = _cell_decimal(row["scores_raw"][f])
                except ValueError as e:
                    score_err = fail(f, str(e)); break
                if d is None:
                    continue
                if not (Decimal("0") <= d <= Decimal("100")):
                    score_err = fail(f, f"{_SCORE_LABELS[f]}超出范围（0-100）"); break
                scores[f] = d
            if score_err:
                errors.append(score_err); continue

            # 理论/实践成绩必须成对（合并逻辑仍由 ScoreService 负责）
            if ("mid_theory_score" in scores) != ("mid_practice_score" in scores):
                errors.append(fail("mid_theory_score", "期中理论成绩与实践成绩必须同时填写")); continue
            if ("final_theory_score" in scores) != ("final_practice_score" in scores):
                errors.append(fail("final_theory_score", "期末理论成绩与实践成绩必须同时填写")); continue

            # 实践学时 ↔ 实践成绩强关系（FIX-009 §七）：行级友好错误，权威校验仍由 ScoreService 负责
            course = courses_by_id.get(tc.course_id)
            has_practice = bool(course and course.practice_hours and course.practice_hours > 0)
            any_practice = any(
                k in scores
                for k in ("mid_practice_score", "final_practice_score", "practice_makeup_score")
            )
            if not has_practice and any_practice:
                errors.append(fail("mid_practice_score", "课程无实践学时，不能导入实践成绩")); continue
            if has_practice and ("mid_score" in scores or "final_score" in scores):
                errors.append(fail("mid_score", "课程含实践学时，必须分别导入理论/实践成绩")); continue

            # 补考资格预检（行级友好错误；权威校验与重算仍由 ScoreService 负责）
            if "theory_makeup_score" in scores:
                ft = scores.get("final_theory_score", scores.get("final_score"))
                if ft is None and grade is not None:
                    ft = (
                        grade.final_theory_score
                        if grade.final_theory_score is not None
                        else grade.final_score
                    )
                if ft is None:
                    errors.append(fail(
                        "theory_makeup_score", "理论补考成绩要求期末理论成绩已录入"
                    )); continue
                if ft >= PASS_SCORE:
                    errors.append(fail(
                        "theory_makeup_score", "理论补考只允许在期末理论成绩不及格时录入"
                    )); continue
            if "practice_makeup_score" in scores:
                fp = scores.get("final_practice_score")
                if fp is None and grade is not None:
                    fp = grade.final_practice_score
                if fp is None:
                    errors.append(fail(
                        "practice_makeup_score", "实践补考成绩要求期末实践成绩已录入"
                    )); continue
                if fp >= PASS_SCORE:
                    errors.append(fail(
                        "practice_makeup_score", "实践补考只允许在期末实践成绩不及格时录入"
                    )); continue

            valid_rows.append(
                {"student_id": student.id, "teaching_class_id": tc.id, "scores": scores}
            )

        GradeService(self.db).import_scores(valid_rows)

        return {
            "total": len(rows),
            "success": len(valid_rows),
            "failed": len(errors),
            "errors": errors,
        }
