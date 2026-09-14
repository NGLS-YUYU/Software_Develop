"""学生、教师 Schema。"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

GENDER = "^(MALE|FEMALE|UNKNOWN)$"


# --- 学生 ---
class StudentCreate(BaseModel):
    student_no: str = Field(..., min_length=1, max_length=30, description="学号，同时作为登录名")
    real_name: str = Field(..., min_length=1, max_length=50)
    class_id: int
    gender: str = Field("UNKNOWN", pattern=GENDER)
    birth_date: date | None = None
    enrollment_year: int = Field(..., ge=1900, le=2200)
    email: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)
    password: str | None = Field(
        None, min_length=6, max_length=128, description="不填则默认为学号"
    )


class StudentUpdate(BaseModel):
    real_name: str | None = Field(None, max_length=50)
    class_id: int | None = None
    gender: str | None = Field(None, pattern=GENDER)
    birth_date: date | None = None
    academic_status: str | None = Field(
        None, pattern="^(ENROLLED|SUSPENDED|GRADUATED|WITHDRAWN)$"
    )
    email: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_no: str
    real_name: str = ""
    class_id: int
    class_name: str | None = None
    major_id: int
    major_name: str | None = None
    college_id: int
    college_name: str | None = None
    gender: str
    birth_date: date | None = None
    enrollment_year: int
    academic_status: str
    total_credits: float = 0
    gpa: float | None = None
    email: str | None = None
    phone: str | None = None


# --- 教师 ---
class TeacherCreate(BaseModel):
    teacher_no: str = Field(..., min_length=1, max_length=30, description="工号，同时作为登录名")
    real_name: str = Field(..., min_length=1, max_length=50)
    college_id: int
    title: str | None = Field(
        None, pattern="^(ASSISTANT|LECTURER|ASSOCIATE_PROFESSOR|PROFESSOR)$"
    )
    gender: str = Field("UNKNOWN", pattern=GENDER)
    hire_date: date | None = None
    email: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)
    password: str | None = Field(None, min_length=6, max_length=128)


class TeacherUpdate(BaseModel):
    real_name: str | None = Field(None, max_length=50)
    college_id: int | None = None
    title: str | None = Field(
        None, pattern="^(ASSISTANT|LECTURER|ASSOCIATE_PROFESSOR|PROFESSOR)$"
    )
    gender: str | None = Field(None, pattern=GENDER)
    hire_date: date | None = None
    status: str | None = Field(None, pattern="^(ACTIVE|LEAVE|RETIRED)$")
    email: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=20)


class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_no: str
    real_name: str = ""
    college_id: int
    college_name: str | None = None
    title: str | None = None
    gender: str
    hire_date: date | None = None
    status: str
    email: str | None = None
    phone: str | None = None
