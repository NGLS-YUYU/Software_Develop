"""生成完整演示数据（CLAUDE.md §30）。

至少包含：1 学院 / 2 专业 / 2 班级 / 5 教师 / 20 学生 / 10 课程
      + 教学任务 / 排课 / 选课 / 考试 / 成绩

幂等：可重复执行，不会产生重复记录。

    python -m scripts.seed_demo
"""

import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.course import Course, CoursePrerequisite, CurriculumCourse, CurriculumPlan  # noqa: E402
from app.models.exam import Exam, ExamRoom, ExamStudent  # noqa: E402
from app.models.grade import Grade, GradeStatus, score_to_point  # noqa: E402
from app.models.misc import Announcement, EvaluationTask  # noqa: E402
from app.models.organization import Class, Classroom, College, Major  # noqa: E402
from app.models.person import Student, Teacher  # noqa: E402
from app.models.selection import CourseSelection, SelectionPeriod, SelectionState  # noqa: E402
from app.models.teaching import Schedule, TeachingClass, TeachingTask  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.person import StudentService, TeacherService  # noqa: E402

random.seed(20260915)

SEMESTER = "2026-2027-1"
GRADE_YEAR = 2026

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许"
GIVEN = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "洋",
         "艳", "勇", "军", "杰", "娟", "涛", "明", "超", "秀兰", "霞"]

COURSES = [
    ("CS101", "程序设计基础", "REQUIRED", 4.0, 64, 48, 16),
    ("CS102", "离散数学", "REQUIRED", 3.0, 48, 48, 0),
    ("CS201", "数据结构", "REQUIRED", 4.0, 64, 48, 16),
    ("CS202", "计算机组成原理", "REQUIRED", 3.5, 56, 44, 12),
    ("CS203", "操作系统", "REQUIRED", 4.0, 64, 48, 16),
    ("CS301", "算法设计与分析", "REQUIRED", 3.0, 48, 40, 8),
    ("CS302", "数据库系统原理", "REQUIRED", 3.5, 56, 40, 16),
    ("CS303", "计算机网络", "REQUIRED", 3.0, 48, 40, 8),
    ("CS401", "软件工程", "ELECTIVE", 2.5, 40, 32, 8),
    ("PUB101", "大学英语", "PUBLIC_REQUIRED", 2.0, 32, 32, 0),
]

PREREQS = [("CS201", "CS101"), ("CS301", "CS201"), ("CS302", "CS201"), ("CS203", "CS202")]


def get_or_create(db: Session, model, defaults: dict | None = None, **kw):
    obj = db.execute(select(model).filter_by(**kw)).scalar_one_or_none()
    if obj:
        return obj, False
    obj = model(**kw, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


def main() -> None:
    print("生成演示数据...")
    with SessionLocal() as db:
        # --- 学院 / 专业 / 班级 ---
        college, _ = get_or_create(
            db, College, {"name": "计算机科学与技术学院"}, code="CS"
        )
        majors = []
        for code, name in [("CS01", "计算机科学与技术"), ("CS02", "软件工程")]:
            m, _ = get_or_create(
                db, Major, {"name": name, "college_id": college.id}, code=code
            )
            majors.append(m)

        classes = []
        for i, m in enumerate(majors, 1):
            c, _ = get_or_create(
                db,
                Class,
                {"name": f"{m.name}{GRADE_YEAR}-1班", "major_id": m.id,
                 "grade_year": GRADE_YEAR},
                code=f"{m.code}-{GRADE_YEAR}-1",
            )
            classes.append(c)
        db.commit()
        print(f"  学院 1 / 专业 {len(majors)} / 班级 {len(classes)}")

        # --- 教室 ---
        rooms = []
        for b, n, cap, t in [
            ("A楼", 1, 60, "MULTIMEDIA"), ("A楼", 2, 60, "NORMAL"),
            ("A楼", 3, 90, "NORMAL"), ("B楼", 1, 45, "LAB"),
            ("B楼", 2, 120, "MULTIMEDIA"),
        ]:
            r, _ = get_or_create(
                db, Classroom,
                {"building": b, "capacity": cap, "room_type": t},
                code=f"{b[0]}-{300 + n}",
            )
            rooms.append(r)
        db.commit()
        print(f"  教室 {len(rooms)}")

        # --- 教师 ---
        tsvc = TeacherService(db)
        teachers = []
        titles = ["PROFESSOR", "ASSOCIATE_PROFESSOR", "LECTURER", "LECTURER", "ASSISTANT"]
        for i in range(1, 6):
            no = f"T{i:03d}"
            t = db.execute(
                select(Teacher).where(Teacher.teacher_no == no)
            ).scalar_one_or_none()
            if t is None:
                t = tsvc.create_teacher({
                    "teacher_no": no,
                    "real_name": f"{SURNAMES[i]}{random.choice(GIVEN)}",
                    "college_id": college.id,
                    "title": titles[i - 1],
                    "gender": "MALE" if i % 2 else "FEMALE",
                    "hire_date": date(2015 + i, 9, 1),
                })
            teachers.append(t)
        print(f"  教师 {len(teachers)}")

        # --- 学生 ---
        ssvc = StudentService(db)
        students = []
        for i in range(1, 21):
            no = f"{GRADE_YEAR}{i:04d}"
            s = db.execute(
                select(Student).where(Student.student_no == no)
            ).scalar_one_or_none()
            if s is None:
                s = ssvc.create_student({
                    "student_no": no,
                    "real_name": f"{SURNAMES[i % len(SURNAMES)]}{random.choice(GIVEN)}",
                    "class_id": classes[i % len(classes)].id,
                    "enrollment_year": GRADE_YEAR,
                    "gender": "MALE" if i % 2 else "FEMALE",
                    "birth_date": date(GRADE_YEAR - 18, (i % 12) + 1, (i % 28) + 1),
                })
            students.append(s)
        print(f"  学生 {len(students)}")

        # --- 课程 ---
        courses = {}
        for code, name, ctype, cr, th, theory, prac in COURSES:
            c, _ = get_or_create(
                db, Course,
                {"name": name, "college_id": college.id, "course_type": ctype,
                 "credits": Decimal(str(cr)), "total_hours": th,
                 "theory_hours": theory, "practice_hours": prac},
                code=code,
            )
            courses[code] = c
        db.commit()

        for cc, pc in PREREQS:
            get_or_create(
                db, CoursePrerequisite,
                {"min_score": Decimal("60.00")},
                course_id=courses[cc].id,
                prerequisite_course_id=courses[pc].id,
            )
        db.commit()
        print(f"  课程 {len(courses)} / 先修关系 {len(PREREQS)}")

        # --- 培养方案 ---
        plan, _ = get_or_create(
            db, CurriculumPlan,
            {"name": f"{majors[0].name}{GRADE_YEAR}级培养方案",
             "major_id": majors[0].id, "grade_year": GRADE_YEAR,
             "total_credits_required": Decimal("160.0"),
             "required_credits": Decimal("120.0"),
             "elective_credits": Decimal("40.0"),
             "status": "PUBLISHED"},
            code=f"CP{GRADE_YEAR}",
        )
        db.commit()
        for i, (code, c) in enumerate(courses.items()):
            get_or_create(
                db, CurriculumCourse,
                {"suggested_semester": (i % 8) + 1,
                 "is_required": c.course_type != "ELECTIVE"},
                plan_id=plan.id, course_id=c.id,
            )
        db.commit()
        print(f"  培养方案 1（含 {len(courses)} 门课程）")

        # --- 教学任务 + 教学班 + 排课 ---
        open_codes = ["CS101", "CS102", "PUB101", "CS201", "CS202", "CS302"]
        tcs = []
        slot = 0
        SLOTS = [(1, 1, 2), (1, 3, 4), (2, 1, 2), (2, 3, 4), (3, 1, 2),
                 (3, 3, 4), (4, 1, 2), (4, 3, 4), (5, 1, 2), (5, 3, 4)]
        for idx, code in enumerate(open_codes):
            course = courses[code]
            task, _ = get_or_create(
                db, TeachingTask,
                {"planned_classes": 1, "status": "CONFIRMED"},
                semester=SEMESTER, course_id=course.id, college_id=college.id,
            )
            db.commit()
            tc, created = get_or_create(
                db, TeachingClass,
                {"task_id": task.id, "course_id": course.id, "semester": SEMESTER,
                 "teacher_id": teachers[idx % len(teachers)].id,
                 "capacity": 40, "selection_status": "OPEN"},
                code=f"{code}-{SEMESTER}-01",
            )
            db.commit()
            tcs.append(tc)
            if created or not tc.schedules:
                d, sp, ep = SLOTS[slot % len(SLOTS)]
                slot += 1
                db.add(Schedule(
                    teaching_class_id=tc.id,
                    classroom_id=rooms[idx % len(rooms)].id,
                    day_of_week=d, start_period=sp, end_period=ep,
                    start_week=1, end_week=16, week_type="ALL",
                    semester=SEMESTER,
                ))
                db.commit()
        print(f"  教学任务/教学班 {len(tcs)}（含排课）")

        # --- 选课时间窗口 ---
        now = datetime.now()
        get_or_create(
            db, SelectionPeriod,
            {"start_time": now - timedelta(days=3),
             "end_time": now + timedelta(days=30),
             "status": "ACTIVE"},
            semester=SEMESTER, name=f"{SEMESTER} 正选",
        )
        db.commit()

        # --- 选课 ---
        # 用学生序号确定性地挑课，而不是全局 random。
        # 否则第二次运行时随机序列已被前面的跳过逻辑改变，
        # 会挑到不同的课，导致重复执行产生新数据（破坏幂等）。
        n_sel = 0
        for i, stu in enumerate(students):
            k = 3 + (i % 3)
            picks = [tcs[(i + j) % len(tcs)] for j in range(k)]
            for tc in picks:
                exists = db.execute(
                    select(CourseSelection).where(
                        CourseSelection.student_id == stu.id,
                        CourseSelection.teaching_class_id == tc.id,
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                if tc.selected_count >= tc.capacity:
                    continue
                db.add(CourseSelection(
                    student_id=stu.id, teaching_class_id=tc.id,
                    course_id=tc.course_id, semester=SEMESTER,
                ))
                tc.selected_count += 1
                n_sel += 1
        db.commit()
        print(f"  选课记录 {n_sel}")

        # --- 成绩（前 3 个教学班出成绩并审核通过）---
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
        n_grade = 0
        for tc in tcs[:3]:
            course = db.get(Course, tc.course_id)
            sels = db.execute(
                select(CourseSelection).where(
                    CourseSelection.teaching_class_id == tc.id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars()
            for sel in sels:
                g = db.execute(
                    select(Grade).where(
                        Grade.student_id == sel.student_id,
                        Grade.teaching_class_id == tc.id,
                    )
                ).scalar_one_or_none()
                if g:
                    continue
                # 分数同样确定性生成，保证重复执行结果一致
                seed_n = (sel.student_id * 7 + tc.id * 13) % 100
                reg = Decimal(str(70 + seed_n % 29))
                fin = Decimal(str(55 + seed_n % 45))
                g = Grade(
                    student_id=sel.student_id, teaching_class_id=tc.id,
                    course_id=tc.course_id, semester=SEMESTER,
                    credits=course.credits, regular_score=reg, final_score=fin,
                    status=GradeStatus.APPROVED,
                    submitted_by=tc.teacher_id, submitted_at=now,
                    approved_by=admin.id, approved_at=now,
                )
                g.compute(course.regular_weight, course.final_weight)
                db.add(g)
                n_grade += 1
        db.commit()
        print(f"  成绩记录 {n_grade}（已审核）")

        # 重算学分绩点
        from app.services.grade import GradeService
        GradeService(db)._refresh_student_credits({s.id for s in students})

        # --- 考试 ---
        n_exam = 0
        for i, tc in enumerate(tcs[:4]):
            e = db.execute(
                select(Exam).where(
                    Exam.teaching_class_id == tc.id, Exam.exam_type == "FINAL"
                )
            ).scalar_one_or_none()
            if e:
                continue
            e = Exam(
                teaching_class_id=tc.id, course_id=tc.course_id, semester=SEMESTER,
                exam_type="FINAL",
                exam_date=date.today() + timedelta(days=60 + i),
                start_time=time(9, 0), end_time=time(11, 0),
                duration_minutes=120, status="PUBLISHED",
            )
            db.add(e)
            db.flush()
            room = rooms[i % len(rooms)]
            er = ExamRoom(exam_id=e.id, classroom_id=room.id, capacity=room.capacity,
                          invigilator_id=teachers[i % len(teachers)].id)
            db.add(er)
            db.flush()
            sids = list(db.execute(
                select(CourseSelection.student_id).where(
                    CourseSelection.teaching_class_id == tc.id,
                    CourseSelection.status == SelectionState.SELECTED,
                )
            ).scalars())
            for seat, sid in enumerate(sids, 1):
                db.add(ExamStudent(exam_room_id=er.id, student_id=sid, seat_no=seat))
            er.assigned_count = len(sids)
            n_exam += 1
        db.commit()
        print(f"  考试 {n_exam}（含考场与座位）")

        # --- 评价任务 + 公告 ---
        get_or_create(
            db, EvaluationTask,
            {"start_time": now - timedelta(days=1),
             "end_time": now + timedelta(days=30), "status": "ACTIVE"},
            name=f"{SEMESTER} 期末教学评价", semester=SEMESTER,
        )
        for title, content, target in [
            ("关于开展 2026-2027 学年第一学期选课工作的通知",
             "请各位同学于选课时间内登录教务系统完成选课。", "STUDENT"),
            ("期末考试安排已发布", "请各位同学及时查看本人考试安排。", "STUDENT"),
            ("关于成绩录入工作的通知", "请各位任课教师于规定时间内完成成绩录入并提交。", "TEACHER"),
        ]:
            a, created = get_or_create(
                db, Announcement,
                {"content": content, "target_type": target,
                 "publisher_id": admin.id, "status": "PUBLISHED",
                 "published_at": now},
                title=title,
            )
        db.commit()
        print("  评价任务 1 / 公告 3")

    print("\n完成。演示账号：")
    print("  教务  admin   / admin123")
    print("  教师  T001    / T001")
    print(f"  学生  {GRADE_YEAR}0001 / {GRADE_YEAR}0001")


if __name__ == "__main__":
    main()
