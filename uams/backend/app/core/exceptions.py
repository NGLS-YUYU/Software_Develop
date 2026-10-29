"""统一业务异常与错误码。

PRD §13.2 要求 API 错误返回可识别的错误码和说明。
"""

from fastapi import HTTPException, status


class BizError(HTTPException):
    """业务异常基类。

    响应体形如 {"code": "AUTH_INVALID_CREDENTIALS", "message": "..."}。
    """

    code = "BIZ_ERROR"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "业务处理失败"

    def __init__(self, message: str | None = None, **extra):
        self.extra = extra
        super().__init__(
            status_code=self.http_status,
            detail={"code": self.code, "message": message or self.message, **extra},
        )


# --- 认证 ---
class InvalidCredentials(BizError):
    code = "AUTH_INVALID_CREDENTIALS"
    http_status = status.HTTP_401_UNAUTHORIZED
    # 用户名、姓名、密码统一提示，避免泄露具体失败字段。
    message = "用户名、姓名或密码错误"


class AccountLocked(BizError):
    code = "AUTH_ACCOUNT_LOCKED"
    http_status = status.HTTP_423_LOCKED
    message = "账号已被锁定，请稍后再试"


class AccountDisabled(BizError):
    code = "AUTH_ACCOUNT_DISABLED"
    http_status = status.HTTP_403_FORBIDDEN
    message = "账号已被停用"


class InvalidToken(BizError):
    code = "AUTH_INVALID_TOKEN"
    http_status = status.HTTP_401_UNAUTHORIZED
    message = "登录状态无效或已过期"


# --- 权限 ---
class PermissionDenied(BizError):
    code = "PERM_DENIED"
    http_status = status.HTTP_403_FORBIDDEN
    message = "无权执行该操作"


# --- 资源 ---
class NotFound(BizError):
    code = "RESOURCE_NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND
    message = "资源不存在"


class Conflict(BizError):
    code = "RESOURCE_CONFLICT"
    http_status = status.HTTP_409_CONFLICT
    message = "资源冲突"


class InvalidEmail(BizError):
    """邮箱格式不合法（FIX-001；Schema 层通常先返回 422）。"""

    code = "INVALID_EMAIL"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "邮箱格式不正确"


class EmailAlreadyExists(Conflict):
    """邮箱已被其他账号占用（FIX-001）。"""

    code = "EMAIL_ALREADY_EXISTS"
    message = "邮箱已存在，请更换邮箱"


class CourseHoursMismatch(BizError):
    """课程理论 + 实践学时 ≠ 总学时（FIX-009 §五）。"""

    code = "COURSE_HOURS_MISMATCH"
    http_status = status.HTTP_400_BAD_REQUEST
    message = "理论课时 + 实践课时必须等于总学时"


# --- 教学班专项（TASK-012） ---
# 复用现有 Conflict（409）体系，仅扩展出更精确的错误码，供前端区分处理。
class TeachingClassFull(Conflict):
    code = "TEACHING_CLASS_FULL"
    message = "教学班容量已满"


class TeachingClassHasData(Conflict):
    code = "TEACHING_CLASS_HAS_DATA"
    message = "教学班存在选课或成绩数据，无法删除"


class TeachingClassTermEnded(Conflict):
    code = "TEACHING_CLASS_TERM_ENDED"
    message = "该学期已结束，不能操作教学班"


class TeachingClassTeacherLocked(Conflict):
    code = "TEACHING_CLASS_TEACHER_LOCKED"
    message = "该教学班已有成绩提交或审核，无法更换教师"


class CapacityBelowEnrolled(Conflict):
    code = "CAPACITY_BELOW_ENROLLED"
    message = "容量不能小于已选人数"


class TeachingClassCourseImmutable(Conflict):
    code = "TEACHING_CLASS_COURSE_IMMUTABLE"
    message = "教学班所属课程不可修改"


class TeachingClassTermImmutable(Conflict):
    code = "TEACHING_CLASS_TERM_IMMUTABLE"
    message = "教学班所属学期不可修改"


# --- 排课专项（TASK-013） ---
class TeachingScheduleTermEnded(Conflict):
    code = "TEACHING_SCHEDULE_TERM_ENDED"
    message = "该学期已结束，不能操作教学安排"


class TeachingScheduleTeacherConflict(Conflict):
    code = "TEACHING_SCHEDULE_TEACHER_CONFLICT"
    message = "该教师在该时段已有其他教学安排"


class TeachingScheduleClassroomConflict(Conflict):
    code = "TEACHING_SCHEDULE_CLASSROOM_CONFLICT"
    message = "该教室在该时段已被占用"


class TeachingScheduleClassConflict(Conflict):
    code = "TEACHING_SCHEDULE_CLASS_CONFLICT"
    message = "该教学班在该时段已有其他教学安排"
