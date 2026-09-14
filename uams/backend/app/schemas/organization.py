"""组织结构 Schema。"""

from pydantic import BaseModel, ConfigDict, Field


# --- 学院 ---
class CollegeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class CollegeCreate(CollegeBase):
    pass


class CollegeUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    status: str | None = Field(None, pattern="^(ACTIVE|INACTIVE)$")


class CollegeOut(CollegeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# --- 专业 ---
class MajorBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    college_id: int
    degree_type: str = Field("BACHELOR", pattern="^(BACHELOR|MASTER|DOCTOR)$")
    duration_years: int = Field(4, ge=1, le=10)
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class MajorCreate(MajorBase):
    pass


class MajorUpdate(BaseModel):
    code: str | None = Field(None, max_length=20)
    name: str | None = Field(None, max_length=100)
    college_id: int | None = None
    degree_type: str | None = Field(None, pattern="^(BACHELOR|MASTER|DOCTOR)$")
    duration_years: int | None = Field(None, ge=1, le=10)
    status: str | None = Field(None, pattern="^(ACTIVE|INACTIVE)$")


class MajorOut(MajorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    college_name: str | None = None


# --- 班级 ---
class ClassBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=60)
    major_id: int
    grade_year: int = Field(..., ge=1900, le=2200)
    counselor_id: int | None = None
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    code: str | None = Field(None, max_length=30)
    name: str | None = Field(None, max_length=60)
    major_id: int | None = None
    grade_year: int | None = Field(None, ge=1900, le=2200)
    counselor_id: int | None = None
    status: str | None = Field(None, pattern="^(ACTIVE|INACTIVE)$")


class ClassOut(ClassBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_count: int = 0
    major_name: str | None = None


# --- 教室 ---
class ClassroomBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    building: str = Field(..., min_length=1, max_length=50)
    capacity: int = Field(..., gt=0, le=2000)
    room_type: str = Field("NORMAL", pattern="^(NORMAL|LAB|MULTIMEDIA)$")
    status: str = Field("ACTIVE", pattern="^(ACTIVE|MAINTENANCE|DISABLED)$")


class ClassroomCreate(ClassroomBase):
    pass


class ClassroomUpdate(BaseModel):
    code: str | None = Field(None, max_length=30)
    building: str | None = Field(None, max_length=50)
    capacity: int | None = Field(None, gt=0, le=2000)
    room_type: str | None = Field(None, pattern="^(NORMAL|LAB|MULTIMEDIA)$")
    status: str | None = Field(None, pattern="^(ACTIVE|MAINTENANCE|DISABLED)$")


class ClassroomOut(ClassroomBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
