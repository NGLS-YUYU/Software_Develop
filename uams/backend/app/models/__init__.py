"""模型集中导入。

Alembic autogenerate 依赖这里的导入来发现所有表，
新增模型必须在此登记，否则迁移会漏表。
"""

from app.db.base import Base
from app.models.course import (
    Course,
    CoursePrerequisite,
    CourseType,
    CurriculumCourse,
    CurriculumPlan,
)
from app.models.exam import Exam, ExamRoom, ExamStudent, ExamType
from app.models.grade import (
    GRADE_POINT_TABLE,
    Grade,
    GradeStatus,
    score_to_point,
)
from app.models.misc import (
    Announcement,
    Evaluation,
    EvaluationTask,
    OperationLog,
)
from app.models.organization import Class, Classroom, College, Major
from app.models.person import AcademicStatus, Student, Teacher
from app.models.role import (
    Permission,
    Role,
    RoleCode,
    RolePermission,
    UserRole,
)
from app.models.selection import (
    CourseSelection,
    SelectionPeriod,
    SelectionState,
)
from app.models.teaching import (
    Schedule,
    SelectionStatus,
    TeachingClass,
    TeachingTask,
    WeekType,
)
from app.models.user import User, UserStatus, UserType

__all__ = [
    "Base",
    # 认证权限
    "User", "UserType", "UserStatus",
    "Role", "RoleCode", "Permission", "UserRole", "RolePermission",
    # 组织
    "College", "Major", "Class", "Classroom",
    # 人员
    "Student", "Teacher", "AcademicStatus",
    # 课程
    "Course", "CourseType", "CoursePrerequisite",
    "CurriculumPlan", "CurriculumCourse",
    # 教学
    "TeachingTask", "TeachingClass", "Schedule", "SelectionStatus", "WeekType",
    # 选课
    "CourseSelection", "SelectionPeriod", "SelectionState",
    # 成绩
    "Grade", "GradeStatus", "score_to_point", "GRADE_POINT_TABLE",
    # 考试
    "Exam", "ExamRoom", "ExamStudent", "ExamType",
    # 其他
    "EvaluationTask", "Evaluation", "Announcement", "OperationLog",
]
