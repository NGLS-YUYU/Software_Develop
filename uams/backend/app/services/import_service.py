"""Excel 批量导入业务逻辑（TASK-010 / FIX-005）。

架构约束（CLAUDE.md §22 / V2.0 指南）：
  - 学生导入：ImportService → StudentService（复用用户/学生创建 + RBAC）
  - 教师导入：ImportService → TeacherService（复用用户/教师创建 + RBAC）
  - 课程导入：ImportService → CourseService
  - 成绩导入：ImportService → GradeService → ScoreService（禁止自行计算成绩）
  - 禁止跨层直接操作数据库；不自动创建学院/专业/班级/教学班/教师/选课
  - 成绩导入一律保存为 DRAFT，不写 GPA / 排名

FIX-005 补充：
  - 模板表头用中文（同时兼容旧的英文字段名），模板附「填写说明」工作表；
  - 成绩模板按教学班 + AssessmentProfile 动态生成（学号/姓名/班级 系统生成，教师只填成绩）；
  - 教师导入教师本人只能操作自己的教学班（路由层传入 current 用户做归属校验）。
"""

from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.models.course import Course, CourseType
from app.models.grade import PASS_SCORE, Grade, GradeStatus
from app.models.organization import Class, College, Major
from app.models.person import Student, Teacher
from app.models.selection import CourseSelection, SelectionState
from app.models.teaching import TeachingClass
from app.models.user import User, UserType
from app.services.assessment import profile_for
from app.services.course import CourseService
from app.services.grade import GradeService
from app.services.person import StudentService, TeacherService

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- 模板字段定义（与 V2.0 指南一致） ---
_STUDENT_HEADERS = ["student_no", "name", "username", "college", "major", "class_name"]
_TEACHER_HEADERS = ["teacher_no", "name", "college", "title", "gender", "phone"]
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

# --- 中文表头 ←→ 后端字段名（FIX-005 §五：模板第一行用中文字段名）---
# 旧的英文字段名仍然接受，保证既有模板与调用方不被打断。
_HEADER_ALIASES: dict[str, str] = {
    # 学生
    "学号": "student_no", "姓名": "name", "登录名": "username",
    "学院": "college", "专业": "major", "行政班": "class_name", "班级": "class_name",
    # 教师
    "工号": "teacher_no", "职称": "title", "性别": "gender",
    "联系电话": "phone", "联系方式": "phone", "入职日期": "hire_date",
    # 课程
    "课程代码": "course_code", "课程编号": "course_code", "课程名称": "course_name",
    "学分": "credits", "总学时": "total_hours",
    "理论学时": "theory_hours", "实践学时": "practice_hours", "课程性质": "course_type",
    # 成绩
    "课程代码(固定)": "course_code", "课程名称(固定)": "course_name",
    "教学班": "teaching_class_code", "教学班编号": "teaching_class_code",
    "平时成绩": "regular_score",
    "期中成绩": "mid_score", "期中理论": "mid_theory_score", "期中实践": "mid_practice_score",
    "期末成绩": "final_score", "期末理论": "final_theory_score",
    "期末实践": "final_practice_score",
    "补考成绩": "theory_makeup_score", "理论补考": "theory_makeup_score",
    "实践补考": "practice_makeup_score",
}

_GRADE_SCORE_LABELS = {
    "regular_score": "平时成绩",
    "mid_score": "期中成绩",
    "mid_theory_score": "期中理论",
    "mid_practice_score": "期中实践",
    "final_score": "期末成绩",
    "final_theory_score": "期末理论",
    "final_practice_score": "期末实践",
    "theory_makeup_score": "补考成绩",
    "practice_makeup_score": "实践补考",
}

# 中文取值 ←→ 枚举值（模板给中文，导入时翻译）
_TITLE_VALUES = {
    "教授": "PROFESSOR", "副教授": "ASSOCIATE_PROFESSOR",
    "讲师": "LECTURER", "助教": "ASSISTANT",
}
_GENDER_VALUES = {"男": "MALE", "女": "FEMALE", "未知": "UNKNOWN"}
_COURSE_TYPE_VALUES = {
    "专业必修": "REQUIRED", "专业选修": "ELECTIVE",
    "公共必修": "PUBLIC_REQUIRED", "公共选修": "PUBLIC_ELECTIVE", "实践": "PRACTICE",
}
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


def _header_map(ws, aliases: dict[str, str] | None = None) -> dict[str, int]:
    """读取首行表头 → {后端字段名: 列号}。

    支持中文表头（FIX-005 §五）与旧的英文字段名：先按别名表翻译，
    翻译不到则原样保留（因此英文表头行为与改动前完全一致）。
    """
    aliases = aliases if aliases is not None else _HEADER_ALIASES
    hmap: dict[str, int] = {}
    for idx in range(1, ws.max_column + 1):
        key = _cell_str(ws.cell(row=1, column=idx).value)
        if not key:
            continue
        hmap[aliases.get(key, key)] = idx
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


_HEADER_FILL = PatternFill("solid", fgColor="D9E7F5")
_LOCKED_FILL = PatternFill("solid", fgColor="F2F2F2")
_HEADER_FONT = Font(bold=True)


def _write_sheet(ws, headers: list[str], rows: list[list], locked_cols: int = 0) -> None:
    """写入表头 + 数据行，并做基础排版（表头底色、灰底固定列、列宽）。

    第 1 行必须是后端能识别的字段名（中文或英文），解析器只读这一行。
    固定列（系统生成、教师不可改）用浅灰底提示，其余列为填写区。
    """
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in rows:
        ws.append(row)
    for idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 16
        if locked_cols and idx <= locked_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(r, idx).fill = _LOCKED_FILL


def _add_notes_sheet(wb, title: str, notes: list[str]) -> None:
    """追加「填写说明」工作表（说明不放在数据行，避免被当成数据解析）。"""
    ws = wb.create_sheet("填写说明")
    ws.column_dimensions["A"].width = 100
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    for line in notes:
        ws.append([line])
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(1, 1).alignment = Alignment(vertical="center")


def _template_bytes(
    headers: list[str],
    example: list | None = None,
    rows: list[list] | None = None,
    title: str = "",
    notes: list[str] | None = None,
    locked_cols: int = 0,
) -> bytes:
    """生成模板工作簿：首个工作表是数据区，第二个工作表是填写说明。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "导入模板"
    body = rows if rows is not None else ([example] if example is not None else [])
    _write_sheet(ws, headers, body, locked_cols=locked_cols)
    if notes:
        _add_notes_sheet(wb, title or "填写说明", notes)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _label_of(field: str) -> str:
    """后端字段名 → 模板中文表头。"""
    for label, name in _HEADER_ALIASES.items():
        if name == field and not label.endswith("(固定)"):
            return label
    return field


def _translate(value: str, mapping: dict[str, str], label: str) -> str:
    """把模板里的中文取值翻译成枚举值；已是枚举值则原样返回。"""
    if not value:
        return value
    if value in mapping.values():
        return value
    translated = mapping.get(value)
    if translated is None:
        allowed = "、".join(mapping.keys())
        raise ValueError(f"{label}非法：{value}（可填：{allowed}）")
    return translated


class ImportService:
    """Excel 批量导入。"""

    def __init__(self, db: Session):
        self.db = db

    # =========================== 模板下载 ===========================

    def student_template(self) -> bytes:
        return _template_bytes(
            [_label_of(f) for f in _STUDENT_HEADERS],
            ["20240001", "张三", "20240001", "信息工程学院", "软件工程", "软件2401班"],
            title="学生批量导入模板",
            notes=[
                "① 学号：必填，唯一，作为学生的登录名（可另填「登录名」列覆盖）。",
                "② 姓名：必填。",
                "③ 学院 / 专业 / 行政班：必填，必须与系统中已存在的名称完全一致；",
                "   三者层级必须匹配（专业属于该学院、行政班属于该专业），系统不会自动创建。",
                "④ 入学年份由行政班的年级自动带入，无需填写。",
                "⑤ 首行表头请勿修改或删除；从第 2 行开始填写数据，可留空行。",
                "⑥ 支持 .xlsx 格式，单个文件不超过 10MB。",
            ],
        )

    def teacher_template(self) -> bytes:
        return _template_bytes(
            [_label_of(f) for f in _TEACHER_HEADERS],
            ["T100", "李四", "信息工程学院", "讲师", "男", "13800000000"],
            title="教师批量导入模板",
            notes=[
                "① 工号：必填，唯一，同时作为教师的登录名；初始密码与工号相同。",
                "② 姓名：必填。",
                "③ 学院：必填，必须与系统中已存在的学院名称完全一致，系统不会自动创建。",
                "④ 职称：选填，可填 教授 / 副教授 / 讲师 / 助教（也可直接填 PROFESSOR 等英文值）。",
                "⑤ 性别：选填，可填 男 / 女 / 未知。",
                "⑥ 联系电话：选填。",
                "⑦ 首行表头请勿修改或删除；从第 2 行开始填写数据，可留空行。",
                "⑧ 支持 .xlsx 格式，单个文件不超过 10MB。",
            ],
        )

    def course_template(self) -> bytes:
        return _template_bytes(
            [_label_of(f) for f in _COURSE_HEADERS],
            ["CS101", "程序设计基础", "信息工程学院", 4.0, 64, 40, 24, "专业必修"],
            title="课程批量导入模板",
            notes=[
                "① 课程代码：必填，唯一。课程名称：必填。",
                "② 学院：必填，必须与系统中已存在的学院名称完全一致，系统不会自动创建。",
                "③ 学分：必填，大于 0（本项目暂无学时→学分的自动换算规则，需人工填写）。",
                "④ 总学时 / 理论学时 / 实践学时：必填，必须满足「理论学时 + 实践学时 = 总学时」。",
                "⑤ 考核方式由总学时自动决定，无需也不能填写：",
                "   总学时 ≤ 32 → 平时 20% + 期末 80%（无期中）；",
                "   总学时 > 32 → 平时 20% + 期中 30% + 期末 50%。",
                "   实践学时 > 0 的课程才有实践考试与实践成绩。",
                "⑥ 课程性质：可填 专业必修 / 专业选修 / 公共必修 / 公共选修 / 实践"
                "（也可填 REQUIRED 等英文值）。",
                "⑦ 首行表头请勿修改或删除；从第 2 行开始填写数据，可留空行。",
                "⑧ 支持 .xlsx 格式，单个文件不超过 10MB。",
            ],
        )

    def grade_template(self, teaching_class_id: int) -> bytes:
        """按教学班动态生成成绩录入模板（FIX-005 §六/§七）。

        - 学生名单、学号、姓名、班级、课程、教学班由系统生成，教师不用填；
        - 成绩列由课程 AssessmentProfile 决定（是否有期中 / 是否有实践）；
        - 已录入的草稿成绩回填，方便教师在此基础上修改后重新上传；
        - 总评/绩点不在模板内计算，导入后由后端 ScoreService 统一计算。
        """
        tc = self.db.get(TeachingClass, teaching_class_id)
        if tc is None:
            raise NotFound(f"教学班不存在（id={teaching_class_id}）")
        course = self.db.get(Course, tc.course_id)
        if course is None:
            raise NotFound("教学班所属课程不存在")
        profile = profile_for(course)

        score_fields = ["regular_score"]
        if profile.has_midterm:
            score_fields += (
                ["mid_theory_score", "mid_practice_score"]
                if profile.has_practice
                else ["mid_score"]
            )
        score_fields += (
            ["final_theory_score", "final_practice_score"]
            if profile.has_practice
            else ["final_score"]
        )
        # 补考列：只给理论补考；实践课额外给实践补考
        score_fields.append("theory_makeup_score")
        if profile.has_practice:
            score_fields.append("practice_makeup_score")

        fixed_fields = [
            "student_no", "name", "class_name",
            "course_code", "course_name", "teaching_class_code",
        ]
        # 显式指定固定列表头（「班级」在学生导入模板里叫「行政班」，沿用别名表会串名）
        fixed_labels = ["学号", "姓名", "班级", "课程代码", "课程名称", "教学班"]
        # 实践课的补考列必须区分「理论补考 / 实践补考」
        score_labels = [
            "理论补考" if f == "theory_makeup_score" and profile.has_practice
            else _GRADE_SCORE_LABELS[f]
            for f in score_fields
        ]
        headers = fixed_labels + score_labels

        selections = list(
            self.db.execute(
                select(CourseSelection)
                .where(
                    CourseSelection.teaching_class_id == teaching_class_id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
        )
        grades = {
            g.student_id: g
            for g in self.db.execute(
                select(Grade).where(Grade.teaching_class_id == teaching_class_id)
            ).scalars()
        }

        rows: list[list] = []
        for sel in sorted(
            selections, key=lambda s: s.student.student_no if s.student else ""
        ):
            stu = sel.student
            if stu is None:
                continue
            g = grades.get(stu.id)
            rows.append(
                [
                    stu.student_no,
                    stu.user.real_name if stu.user else "",
                    stu.klass.name if stu.klass else "",
                    course.code,
                    course.name,
                    tc.code,
                ]
                + [
                    (float(getattr(g, f)) if g and getattr(g, f) is not None else "")
                    for f in score_fields
                ]
            )

        weight = (
            "平时 20% + 期中 30% + 期末 50%"
            if profile.has_midterm
            else "平时 20% + 期末 80%"
        )
        if profile.has_practice:
            weight += "；理论/实践分别计算后取两侧平均"
        return _template_bytes(
            headers,
            rows=rows,
            title=f"成绩录入模板：{course.name}（{course.code}）",
            locked_cols=len(fixed_fields),
            notes=[
                f"课程：{course.name}（{course.code}）　教学班：{tc.code}　"
                f"总学时 {course.total_hours}（理论 {course.theory_hours} / "
                f"实践 {course.practice_hours}）",
                f"成绩构成：{weight}。",
                "",
                "① 灰色列（学号 / 姓名 / 班级 / 课程代码 / 课程名称 / 教学班）由系统生成，"
                "请勿修改；改了会找不到学生或教学班。",
                "② 只需填写右侧的成绩列，每格 0~100 分，留空表示暂不录入。",
                "③ 本模板不计算总评：总评、绩点、是否及格全部由系统按课程考核方式统一计算。",
            ]
            + (
                ["④ 本课程含实践学时，期中/期末的理论与实践成绩必须成对填写。"]
                if profile.has_practice
                else []
            )
            + (
                []
                if profile.has_midterm
                else ["④ 本课程为 32 学时两段式，没有期中考试，模板已隐藏期中列。"]
            )
            + [
                "⑤ 补考成绩只允许在对应期末成绩不及格（<60）时填写。",
                "⑥ 已提交/已审核的成绩不能通过导入覆盖，请先由教务驳回。",
            ],
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

    # =========================== 教师导入 ===========================

    def import_teachers(self, file_bytes: bytes) -> dict:
        ws = _load_sheet(file_bytes)
        hmap = _header_map(ws)
        _require_headers(hmap, ["teacher_no", "name", "college"])

        rows: list[dict] = []
        college_vals: set[str] = set()
        no_vals: set[str] = set()
        for r in range(2, ws.max_row + 1):
            teacher_no = _cell_str(ws.cell(r, hmap["teacher_no"]).value)
            name = _cell_str(ws.cell(r, hmap["name"]).value)
            college_v = _cell_str(ws.cell(r, hmap["college"]).value)
            title_v = _cell_str(ws.cell(r, hmap["title"]).value) if "title" in hmap else ""
            gender_v = _cell_str(ws.cell(r, hmap["gender"]).value) if "gender" in hmap else ""
            phone_v = _cell_str(ws.cell(r, hmap["phone"]).value) if "phone" in hmap else ""
            if not any([teacher_no, name, college_v, title_v, gender_v, phone_v]):
                continue
            rows.append(
                {
                    "row": r, "teacher_no": teacher_no, "name": name,
                    "college": college_v, "title": title_v, "gender": gender_v,
                    "phone": phone_v,
                }
            )
            college_vals.add(college_v)
            no_vals.add(teacher_no)

        colleges = _load_refs(self.db, College, college_vals)
        existing_nos = set(
            self.db.execute(
                select(Teacher.teacher_no).where(Teacher.teacher_no.in_(no_vals))
            ).scalars()
        )
        existing_usernames = set(
            self.db.execute(select(User.username).where(User.username.in_(no_vals))).scalars()
        )

        svc = TeacherService(self.db)
        errors: list[dict] = []
        seen: set[str] = set()
        success = 0
        for row in rows:
            r = row["row"]

            def fail(field: str, msg: str) -> dict:
                return {"row": r, "field": field, "message": msg}

            if not row["teacher_no"]:
                errors.append(fail("teacher_no", "工号不能为空")); continue
            if not row["name"]:
                errors.append(fail("name", "姓名不能为空")); continue
            if not row["college"]:
                errors.append(fail("college", "学院不能为空")); continue
            college = _lookup(colleges, row["college"])
            if college is None:
                errors.append(fail("college", f"学院不存在：{row['college']}")); continue

            try:
                title = _translate(row["title"], _TITLE_VALUES, "职称") or None
            except ValueError as e:
                errors.append(fail("title", str(e))); continue
            try:
                gender = _translate(row["gender"], _GENDER_VALUES, "性别") or "UNKNOWN"
            except ValueError as e:
                errors.append(fail("gender", str(e))); continue

            if row["teacher_no"] in existing_nos:
                errors.append(fail("teacher_no", f"工号已存在：{row['teacher_no']}")); continue
            if row["teacher_no"] in seen:
                errors.append(fail("teacher_no", f"工号在导入文件中重复：{row['teacher_no']}")); continue
            if row["teacher_no"] in existing_usernames:
                errors.append(fail("teacher_no", f"登录名已被占用：{row['teacher_no']}")); continue

            seen.add(row["teacher_no"])
            svc.create_teacher(
                {
                    "teacher_no": row["teacher_no"],
                    "real_name": row["name"],
                    "college_id": college.id,
                    "title": title,
                    "gender": gender,
                    "phone": row["phone"] or None,
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

            try:
                ctype = _translate(row["course_type"], _COURSE_TYPE_VALUES, "课程性质")
            except ValueError as e:
                errors.append(fail("course_type", str(e))); continue
            if ctype not in CourseType.ALL:
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
                    "course_type": ctype,
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

    def import_grades(self, file_bytes: bytes, current: User | None = None) -> dict:
        """导入成绩（FIX-005：模板由教学班动态生成，成绩列按课程考核结构裁剪）。

        ``current`` 传入调用者时按角色做归属校验：教师只能导入本人授课教学班的成绩
        （CLAUDE.md §9：后端必须做对象级权限校验，不能只靠前端隐藏入口）。
        """
        ws = _load_sheet(file_bytes)
        hmap = _header_map(ws)
        # 成绩模板的列随课程考核结构变化（32h 无期中列、无实践无实践列），
        # 因此只强制要求定位用的两列，成绩列按实际出现的表头解析。
        _require_headers(hmap, ["student_no", "teaching_class_code"])
        present_scores = [f for f in _GRADE_SCORE_FIELDS if f in hmap]

        rows: list[dict] = []
        student_nos: set[str] = set()
        tc_codes: set[str] = set()
        for r in range(2, ws.max_row + 1):
            student_no = _cell_str(ws.cell(r, hmap["student_no"]).value)
            tc_code = _cell_str(ws.cell(r, hmap["teaching_class_code"]).value)
            scores_raw = {f: ws.cell(r, hmap[f]).value for f in present_scores}
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
        me_teacher: Teacher | None = None
        if current is not None and current.user_type == UserType.TEACHER:
            me_teacher = self.db.execute(
                select(Teacher).where(Teacher.user_id == current.id)
            ).scalar_one_or_none()
            if me_teacher is None:
                raise PermissionDenied("教师档案不存在")
        elif current is not None and current.user_type == UserType.STUDENT:
            raise PermissionDenied("学生无权导入成绩")

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
            # 对象级权限：教师只能导入本人授课教学班的成绩（CLAUDE.md §9）
            if me_teacher is not None and tc.teacher_id != me_teacher.id:
                errors.append(fail(
                    "teaching_class_code", f"只能导入本人授课教学班的成绩：{tc.code}"
                )); continue

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
            for f in present_scores:
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
