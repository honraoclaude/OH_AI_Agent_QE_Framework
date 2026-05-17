import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from src.models import RiskLevel, TestCase, TestSuite, TestType, TestingQuadrant, UserStory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "system_prompt.txt").read_text(
    encoding="utf-8"
)

_TOOL_SCHEMA = {
    "name": "generate_test_cases",
    "description": "Output the complete BDD test suite for the given User Story.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scenarios": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "gherkin": {"type": "string"},
                        "risk_score": {"type": "integer", "minimum": 1, "maximum": 10},
                        "risk_rationale": {"type": "string"},
                        "test_type": {"type": "string", "enum": ["UI", "INTEGRATION", "UNIT"]},
                        "automation_candidate": {"type": "boolean"},
                        "automation_rationale": {"type": "string"},
                        "testing_quadrant": {
                            "type": "string",
                            "enum": ["Q1", "Q2", "Q3", "Q4"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "title",
                        "gherkin",
                        "risk_score",
                        "risk_rationale",
                        "test_type",
                        "automation_candidate",
                        "automation_rationale",
                        "testing_quadrant",
                        "tags",
                    ],
                },
            }
        },
        "required": ["scenarios"],
    },
}


def _risk_level(score: int) -> RiskLevel:
    if score >= 7:
        return RiskLevel.HIGH
    if score >= 4:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _build_user_message(story: UserStory) -> str:
    parts = [
        f"Story Key: {story.key}",
        f"Summary: {story.summary}",
    ]
    if story.priority:
        parts.append(f"Priority: {story.priority}")
    if story.story_points:
        parts.append(f"Story Points: {story.story_points}")
    if story.components:
        parts.append(f"Components: {', '.join(story.components)}")
    if story.labels:
        parts.append(f"Labels: {', '.join(story.labels)}")
    if story.description:
        parts.append(f"\nDescription:\n{story.description}")
    if story.acceptance_criteria:
        parts.append(f"\nAcceptance Criteria:\n{story.acceptance_criteria}")
    return "\n".join(parts)


class AIAgent:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate_test_suite(self, story: UserStory) -> TestSuite:
        # Quality gate: refuse to generate for content-free stories
        if not story.description and not story.acceptance_criteria:
            raise ValueError(
                f"{story.key} has no description or acceptance criteria — "
                "generation skipped to avoid low-quality output"
            )

        log = logging.LoggerAdapter(logger, {"story_key": story.key})
        log.info("Starting test suite generation")

        response = self._call_claude(_build_user_message(story))

        log.info(
            "Claude usage — input_tokens=%d output_tokens=%d stop_reason=%s",
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )

        if response.stop_reason == "max_tokens":
            raise ValueError(
                f"Claude output was truncated for {story.key} — "
                f"increase CLAUDE_MAX_TOKENS (currently {settings.claude_max_tokens})"
            )

        tool_use_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if not tool_use_block:
            raise ValueError(f"Claude did not call generate_test_cases for {story.key}")

        test_cases: list[TestCase] = [
            TestCase(
                title=raw["title"],
                gherkin=raw["gherkin"],
                risk_score=raw["risk_score"],
                risk_level=_risk_level(raw["risk_score"]),
                risk_rationale=raw["risk_rationale"],
                test_type=TestType(raw["test_type"]),
                automation_candidate=raw["automation_candidate"],
                automation_rationale=raw["automation_rationale"],
                testing_quadrant=TestingQuadrant(raw["testing_quadrant"]),
                tags=raw.get("tags", []),
            )
            for raw in tool_use_block.input["scenarios"]
        ]

        suite = TestSuite(
            story_key=story.key,
            story_summary=story.summary,
            generated_at=datetime.now(timezone.utc).isoformat(),
            test_cases=test_cases,
        )

        log.info(
            "Generated %d test cases (overall_risk=%s automation_candidates=%d)",
            suite.total_test_cases,
            suite.overall_risk.value,
            suite.automation_candidate_count,
        )
        return suite

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(
            (anthropic.APIStatusError, anthropic.APIConnectionError)
        ),
        reraise=True,
    )
    def _call_claude(self, user_message: str) -> anthropic.types.Message:
        return self._client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "generate_test_cases"},
            messages=[{"role": "user", "content": user_message}],
        )
