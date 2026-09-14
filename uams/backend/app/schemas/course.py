"""课程与培养方案 Schema。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

COURSE_TYPE = "^(REQUIRED|ELECTIVE|PUBLIC_REQUIRED|PUBLIC_ELECTIVE|PRACTICE)$"


class CourseBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=100)
    college_id: int
    course_type: str = Field(..., pattern=COURSE_TYPE)
    credits: Decimal = Field(..., gt=0, le=30)
    total_hours: int = Field(..., ge=0, le=500)
    theory_hours: int = Field(0, ge=0, le=500)
    practice_hours: int = Field(0, ge=0, le=500)
    exam_type: str = Field("EXAM", pattern="^(EXAM|CHECK)$")
    regular_weight: Decimal = Field(Decimal("0.40"), ge=0, le=1)
    final_weight: Decimal = Field(Decimal("0.60"), ge=0, le=1)
    description: str | None = None
    status: str = Field("ACTIVE", pattern="^(ACTIVE|INACTIVE)$")

    @model_validator(mode="after")
    def check_weights(self):
        if self.regular_weight + self.final_weight != Decimal("1"):
            raise ValueError("平时成绩权重与期末成绩权重之和必须等于 1")
        return self


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    code: str | None = Field(None, max_length=30)
    name: str | None = Field(None, max_length=100)
    college_id: int | None = None
    course_type: str | None = Field(None, pattern=COURSE_TYPE)
    credits: Decimal | None = Field(None, gt=0, le=30)
    total_hours: int | None = Field(None, ge=0, le=500)
    theory_hours: int | None = Field(None, ge=0, le=500)
    practice_hours: int | None = Field(None, ge=0, le=500)
    exam_type: str | None = Field(None, pattern="^(EXAM|CHECK)$")
    regular_weight: Decimal | None = Field(None, ge=0, le=1)
    final_weight: Decimal | None = Field(None, ge=0, le=1)
    description: str | None = None
    status: str | None = Field(None, pattern="^(ACTIVE|INACTIVE)$")

    @model_validator(mode="after")
    def check_weights(self):
        if self.regular_weight is not None and self.final_weight is not None:
            if self.regular_weight + self.final_weight != Decimal("1"):
                raise ValueError("平时成绩权重与期末成绩权重之和必须等于 1")
        elif (self.regular_weight is None) != (self.final_weight is None):
            raise ValueError("两项权重必须同时修改")
        return self


class CourseOut(CourseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    college_name: str | None = None


class PrerequisiteCreate(BaseModel):
    prerequisite_course_id: int
    min_score: Decimal = Field(Decimal("60.00"), ge=0, le=100)


class PrerequisiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    prerequisite_course_id: int
    min_score: Decimal
    prerequisite_code: str | None = None
    prerequisite_name: str | None = None


# --- 培养方案 ---
class CurriculumPlanCreate(BaseModel):
    code: str = Field(..., max_length=30)
    name: str = Field(..., max_length=100)
    major_id: int
    grade_year: int = Field(..., ge=1900, le=2200)
    total_credits_required: Decimal = Field(..., gt=0)
    required_credits: Decimal = Field(..., ge=0)
    elective_credits: Decimal = Field(..., ge=0)
    status: str = Field("DRAFT", pattern="^(DRAFT|PUBLISHED|ARCHIVED)$")


class CurriculumPlanUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    total_credits_required: Decimal | None = Field(None, gt=0)
    required_credits: Decimal | None = Field(None, ge=0)
    elective_credits: Decimal | None = Field(None, ge=0)
    status: str | None = Field(None, pattern="^(DRAFT|PUBLISHED|ARCHIVED)$")


class CurriculumPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    major_id: int
    major_name: str | None = None
    grade_year: int
    total_credits_required: Decimal
    required_credits: Decimal
    elective_credits: Decimal
    status: str


class CurriculumCourseCreate(BaseModel):
    course_id: int
    suggested_semester: int = Field(..., ge=1, le=12)
    is_required: bool = True


class CurriculumCourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_id: int
    course_id: int
    suggested_semester: int
    is_required: bool
    course_code: str | None = None
    course_name: str | None = None
    credits: Decimal | None = None
