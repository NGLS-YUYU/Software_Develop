"""学生、教师业务逻辑。

建档时同步创建 users 账号并授予对应角色，两者必须在同一事务内完成。
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import Conflict, NotFound
from app.core.security import hash_password
from app.models.organization import Class, College
from app.models.person import Student, Teacher
from app.models.role import Role, RoleCode, UserRole
from app.models.user import User, UserType
from app.services.base import BaseCrudService


def _link_role(db: Session, user: User, role_code: str) -> None:
    role = db.execute(select(Role).where(Role.code == role_code)).scalar_one_or_none()
    if role is None:
        raise NotFound(f"角色 {role_code} 不存在，请先执行 seed 脚本")
    db.add(UserRole(user_id=user.id, role_id=role.id))


class StudentService(BaseCrudService[Student]):
    model = Student
    unique_fields = ("student_no",)
    default_order = "student_no"
    entity_name = "学生"

    def base_stmt(self) -> Select:
        return select(Student).options(
            selectinload(Student.user),
            selectinload(Student.klass),
            selectinload(Student.major),
            selectinload(Student.college),
        )

    def apply_search(self, stmt: Select, keyword: str | None) -> Select:
        """学号或姓名模糊搜索；姓名在关联的 users 表上。"""
        if not keyword:
            return stmt
        like = f"%{keyword}%"
        return stmt.join(User, Student.user_id == User.id).where(
            (Student.student_no.like(like)) | (User.real_name.like(like))
        )

    def create_student(self, data: dict[str, Any]) -> Student:
        no = data["student_no"]
        if self.db.execute(
            select(Student).where(Student.student_no == no)
        ).scalar_one_or_none():
            raise Conflict(f"学号已存在：{no}")
        if self.db.execute(select(User).where(User.username == no)).scalar_one_or_none():
            raise Conflict(f"登录名已被占用：{no}")

        klass = self.db.get(Class, data["class_id"])
        if klass is None:
            raise NotFound(f"班级不存在（id={data['class_id']}）")
        major = klass.major
        if major is None:
            raise NotFound("班级未关联专业，数据异常")

        user = User(
            username=no,
            # 默认密码为学号本身，首次登录应提示修改
            password_hash=hash_password(data.get("password") or no),
            real_name=data["real_name"],
            user_type=UserType.STUDENT,
            email=data.get("email"),
            phone=data.get("phone"),
        )
        self.db.add(user)
        self.db.flush()
        _link_role(self.db, user, RoleCode.STUDENT)

        student = Student(
            user_id=user.id,
            student_no=no,
            class_id=klass.id,
            # major_id / college_id 为冗余字段，此处由 Service 保证与 class 一致
            major_id=major.id,
            college_id=major.college_id,
            gender=data.get("gender", "UNKNOWN"),
            birth_date=data.get("birth_date"),
            enrollment_year=data["enrollment_year"],
        )
        self.db.add(student)
        klass.student_count = (klass.student_count or 0) + 1
        self._commit()
        return student

    def update_student(self, student_id: int, data: dict[str, Any]) -> Student:
        stu = self.get_or_404(student_id)
        data = {k: v for k, v in data.items() if v is not None}

        if "class_id" in data and data["class_id"] != stu.class_id:
            new_cls = self.db.get(Class, data["class_id"])
            if new_cls is None:
                raise NotFound(f"班级不存在（id={data['class_id']}）")
            old_cls = self.db.get(Class, stu.class_id)
            if old_cls:
                old_cls.student_count = max(0, (old_cls.student_count or 1) - 1)
            new_cls.student_count = (new_cls.student_count or 0) + 1
            stu.class_id = new_cls.id
            stu.major_id = new_cls.major_id
            stu.college_id = new_cls.major.college_id

        for f in ("gender", "birth_date", "academic_status"):
            if f in data:
                setattr(stu, f, data[f])
        for f in ("real_name", "email", "phone"):
            if f in data and stu.user:
                setattr(stu.user, f, data[f])

        self._commit()
        return stu

    def validate_delete(self, obj: Student) -> None:
        from app.models.selection import CourseSelection

        n = self.db.execute(
            select(func.count())
            .select_from(CourseSelection)
            .where(CourseSelection.student_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该学生有 {n} 条选课记录，无法删除")

    def delete(self, obj_id: int) -> None:
        stu = self.get_or_404(obj_id)
        self.validate_delete(stu)
        klass = self.db.get(Class, stu.class_id)
        if klass:
            klass.student_count = max(0, (klass.student_count or 1) - 1)
        user = self.db.get(User, stu.user_id)
        self.db.delete(stu)
        if user:
            self.db.delete(user)  # user_roles 由外键 CASCADE 清理
        self._commit()


class TeacherService(BaseCrudService[Teacher]):
    model = Teacher
    unique_fields = ("teacher_no",)
    default_order = "teacher_no"
    entity_name = "教师"

    def base_stmt(self) -> Select:
        return select(Teacher).options(
            selectinload(Teacher.user), selectinload(Teacher.college)
        )

    def apply_search(self, stmt: Select, keyword: str | None) -> Select:
        if not keyword:
            return stmt
        like = f"%{keyword}%"
        return stmt.join(User, Teacher.user_id == User.id).where(
            (Teacher.teacher_no.like(like)) | (User.real_name.like(like))
        )

    def create_teacher(self, data: dict[str, Any]) -> Teacher:
        no = data["teacher_no"]
        if self.db.execute(
            select(Teacher).where(Teacher.teacher_no == no)
        ).scalar_one_or_none():
            raise Conflict(f"工号已存在：{no}")
        if self.db.execute(select(User).where(User.username == no)).scalar_one_or_none():
            raise Conflict(f"登录名已被占用：{no}")
        if not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")

        user = User(
            username=no,
            password_hash=hash_password(data.get("password") or no),
            real_name=data["real_name"],
            user_type=UserType.TEACHER,
            email=data.get("email"),
            phone=data.get("phone"),
        )
        self.db.add(user)
        self.db.flush()
        _link_role(self.db, user, RoleCode.TEACHER)

        teacher = Teacher(
            user_id=user.id,
            teacher_no=no,
            college_id=data["college_id"],
            title=data.get("title"),
            gender=data.get("gender", "UNKNOWN"),
            hire_date=data.get("hire_date"),
        )
        self.db.add(teacher)
        self._commit()
        return teacher

    def update_teacher(self, teacher_id: int, data: dict[str, Any]) -> Teacher:
        t = self.get_or_404(teacher_id)
        data = {k: v for k, v in data.items() if v is not None}
        if "college_id" in data and not self.db.get(College, data["college_id"]):
            raise NotFound(f"学院不存在（id={data['college_id']}）")
        for f in ("college_id", "title", "gender", "hire_date", "status"):
            if f in data:
                setattr(t, f, data[f])
        for f in ("real_name", "email", "phone"):
            if f in data and t.user:
                setattr(t.user, f, data[f])
        self._commit()
        return t

    def validate_delete(self, obj: Teacher) -> None:
        from app.models.teaching import TeachingClass

        n = self.db.execute(
            select(func.count())
            .select_from(TeachingClass)
            .where(TeachingClass.teacher_id == obj.id)
        ).scalar()
        if n:
            raise Conflict(f"该教师有 {n} 个教学班，无法删除")

    def delete(self, obj_id: int) -> None:
        t = self.get_or_404(obj_id)
        self.validate_delete(t)
        user = self.db.get(User, t.user_id)
        self.db.delete(t)
        if user:
            self.db.delete(user)
        self._commit()
