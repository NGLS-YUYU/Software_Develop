"""课程考核规则服务（FIX-009）。

单一业务来源，贯穿「课程 → 教学班 → 成绩结构 → 教师录入 → 成绩计算」全链路：

- ``Course.total_hours``     → 考核结构（32h 两段式无期中；48/64h 三段式有期中）
- ``Course.practice_hours``  → 是否含实践（practice_hours > 0 才有实践考试/成绩）

ScoreService、成绩 API、教师页面都从这里取考核配置，禁止各自 if/elif 猜课程类型，
禁止用「成绩里有没有实践成绩」反推课程是否实践课（CLAUDE.md §21 / FIX-009 §八、§十四）。

这里不新增数据库表：Course 字段已足够，考核配置由 Service/API 动态计算（FIX-009 §十三）。
"""

from dataclasses import dataclass
from decimal import Decimal

from app.models.course import AssessmentType

# 课程考核权重规则（TASK-003 / FIX-008）：调整比例只改这里，成绩计算唯一来源。
WEIGHT_RULES: dict[str, dict[str, Decimal | None]] = {
    AssessmentType.HOURS_32: {
        "regular": Decimal("0.2"),
        "mid": None,
        "final": Decimal("0.8"),
    },
    AssessmentType.HOURS_48: {
        "regular": Decimal("0.2"),
        "mid": Decimal("0.3"),
        "final": Decimal("0.5"),
    },
    AssessmentType.HOURS_64: {
        "regular": Decimal("0.2"),
        "mid": Decimal("0.3"),
        "final": Decimal("0.5"),
    },
}


def derive_assessment_type(total_hours: int) -> str:
    """按总学时推导考核方式（TASK-003）。

    - ``<= 32`` → "32"（平时 20% + 期末 80%，无期中）
    - ``<= 48`` → "48"（平时 20% + 期中 30% + 期末 50%）
    - 其余      → "64"（与 48 同权重，三段式）
    """
    if total_hours <= 32:
        return AssessmentType.HOURS_32
    if total_hours <= 48:
        return AssessmentType.HOURS_48
    return AssessmentType.HOURS_64


@dataclass(frozen=True)
class AssessmentProfile:
    """课程考核配置（FIX-009 §十三）。"""

    assessment_type: str
    has_midterm: bool
    has_practice: bool
    regular: Decimal
    mid: Decimal | None
    final: Decimal

    @property
    def weights(self) -> dict[str, Decimal | None]:
        return {"regular": self.regular, "mid": self.mid, "final": self.final}


def profile_for(course) -> AssessmentProfile:
    """由课程属性生成考核配置。

    总学时是唯一驱动源：不信任数据库里手工存的 ``assessment_type``（可能因课程
    编辑而漂移），一律按 ``total_hours`` 现算，保证计算规则 == 页面规则。
    """
    total_hours = int(course.total_hours or 0)
    assessment_type = derive_assessment_type(total_hours)
    rule = WEIGHT_RULES[assessment_type]
    return AssessmentProfile(
        assessment_type=assessment_type,
        has_midterm=rule["mid"] is not None,
        has_practice=int(course.practice_hours or 0) > 0,
        regular=rule["regular"],
        mid=rule["mid"],
        final=rule["final"],
    )
