from enum import Enum
from pydantic import BaseModel, Field, computed_field


class TestType(str, Enum):
    UI = "UI"
    INTEGRATION = "INTEGRATION"
    UNIT = "UNIT"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TestingQuadrant(str, Enum):
    Q1 = "Q1"  # Technology-facing, automated — unit/component
    Q2 = "Q2"  # Business-facing, automated — functional/UI regression
    Q3 = "Q3"  # Business-facing, manual — exploratory/UAT
    Q4 = "Q4"  # Technology-facing, tools — performance/security


class UserStory(BaseModel):
    key: str
    summary: str
    description: str | None = None
    acceptance_criteria: str | None = None
    priority: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    story_points: float | None = None


class TestCase(BaseModel):
    title: str
    gherkin: str
    risk_score: int = Field(ge=1, le=10)
    risk_level: RiskLevel
    risk_rationale: str
    test_type: TestType
    automation_candidate: bool
    automation_rationale: str
    testing_quadrant: TestingQuadrant
    tags: list[str] = Field(default_factory=list)
    zephyr_key: str | None = None


class QuadrantSummary(BaseModel):
    Q1: list[str] = Field(default_factory=list)
    Q2: list[str] = Field(default_factory=list)
    Q3: list[str] = Field(default_factory=list)
    Q4: list[str] = Field(default_factory=list)


class TestSuite(BaseModel):
    story_key: str
    story_summary: str
    generated_at: str
    test_cases: list[TestCase] = Field(default_factory=list)

    @computed_field
    @property
    def overall_risk(self) -> RiskLevel:
        if any(tc.risk_level == RiskLevel.HIGH for tc in self.test_cases):
            return RiskLevel.HIGH
        if any(tc.risk_level == RiskLevel.MEDIUM for tc in self.test_cases):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @computed_field
    @property
    def total_test_cases(self) -> int:
        return len(self.test_cases)

    @computed_field
    @property
    def automation_candidate_count(self) -> int:
        return sum(1 for tc in self.test_cases if tc.automation_candidate)

    @computed_field
    @property
    def quadrant_summary(self) -> QuadrantSummary:
        summary = QuadrantSummary()
        for tc in self.test_cases:
            getattr(summary, tc.testing_quadrant.value).append(tc.title)
        return summary


class JiraWebhookEvent(BaseModel):
    model_config = {"extra": "ignore"}

    webhookEvent: str
    issue: dict
    changelog: dict | None = None
