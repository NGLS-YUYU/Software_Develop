"""学期 Schema（TASK-011）。"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.term import TermStatus


class TermCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    academic_year: str = Field(..., min_length=1, max_length=9, description="学年，如 2026-2027")
    semester: int = Field(..., ge=1, le=2, description="学期序号：1 或 2")
    start_date: date
    end_date: date
    status: str = Field(TermStatus.PLANNED, pattern="^(PLANNED|ACTIVE|ENDED)$")

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("结束日期必须晚于开始日期")
        return self


class TermUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    academic_year: str | None = Field(None, min_length=1, max_length=9)
    semester: int | None = Field(None, ge=1, le=2)
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = Field(None, pattern="^(PLANNED|ACTIVE|ENDED)$")

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("结束日期必须晚于开始日期")
        return self


class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    academic_year: str
    semester: int
    start_date: date
    end_date: date
    status: str
    teaching_class_count: int = 0
