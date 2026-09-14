"""开课与排课 Schema。"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

SEMESTER_RE = r"^\d{4}-\d{4}-[1-3]$"


class TeachingTaskCreate(BaseModel):
    semester: str = Field(..., pattern=SEMESTER_RE, description="如 2026-2027-1")
    course_id: int
    college_id: int
    planned_classes: int = Field(1, ge=1, le=50)
    status: str = Field("DRAFT", pattern="^(DRAFT|CONFIRMED|CANCELLED)$")


class TeachingTaskUpdate(BaseModel):
    planned_classes: int | None = Field(None, ge=1, le=50)
    status: str | None = Field(None, pattern="^(DRAFT|CONFIRMED|CANCELLED)$")


class TeachingTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    semester: str
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    college_id: int
    college_name: str | None = None
    planned_classes: int
    status: str
    class_count: int = 0


class TeachingClassCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    task_id: int
    teacher_id: int | None = None
    capacity: int = Field(..., gt=0, le=1000)


class TeachingClassUpdate(BaseModel):
    teacher_id: int | None = None
    capacity: int | None = Field(None, gt=0, le=1000)
    selection_status: str | None = Field(None, pattern="^(CLOSED|OPEN|FINISHED)$")
    status: str | None = Field(None, pattern="^(ACTIVE|CANCELLED)$")


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    teaching_class_id: int
    classroom_id: int
    classroom_code: str | None = None
    building: str | None = None
    day_of_week: int
    start_period: int
    end_period: int
    start_week: int
    end_week: int
    week_type: str
    semester: str


class TeachingClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    task_id: int
    course_id: int
    course_code: str | None = None
    course_name: str | None = None
    credits: float | None = None
    semester: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    capacity: int
    selected_count: int
    remaining: int = 0
    selection_status: str
    status: str
    schedules: list[ScheduleOut] = []


class ScheduleCreate(BaseModel):
    classroom_id: int
    day_of_week: int = Field(..., ge=1, le=7, description="1=周一 … 7=周日")
    start_period: int = Field(..., ge=1, le=14)
    end_period: int = Field(..., ge=1, le=14)
    start_week: int = Field(1, ge=1, le=30)
    end_week: int = Field(16, ge=1, le=30)
    week_type: str = Field("ALL", pattern="^(ALL|ODD|EVEN)$")

    @model_validator(mode="after")
    def check_ranges(self):
        if self.end_period < self.start_period:
            raise ValueError("结束节次不能早于开始节次")
        if self.end_week < self.start_week:
            raise ValueError("结束周不能早于开始周")
        return self


class ConflictInfo(BaseModel):
    type: str = Field(..., description="CLASSROOM / TEACHER / STUDENT")
    message: str
    teaching_class_code: str | None = None
