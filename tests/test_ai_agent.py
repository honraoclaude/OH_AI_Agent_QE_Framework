from unittest.mock import MagicMock, patch

import pytest

from src.ai_agent import AIAgent, _build_user_message, _risk_level
from src.models import RiskLevel, TestCase, TestType, TestingQuadrant, UserStory


def make_test_case(risk_score: int, risk_level: RiskLevel) -> TestCase:
    return TestCase(
        title="Sample scenario",
        gherkin="Given a step\nWhen an action\nThen a result",
        risk_score=risk_score,
        risk_level=risk_level,
        risk_rationale="test",
        test_type=TestType.UI,
        automation_candidate=True,
        automation_rationale="test",
        testing_quadrant=TestingQuadrant.Q2,
        tags=[],
    )


class TestRiskLevel:
    def test_high_boundary(self):
        assert _risk_level(7) == RiskLevel.HIGH

    def test_high_max(self):
        assert _risk_level(10) == RiskLevel.HIGH

    def test_medium_boundary(self):
        assert _risk_level(4) == RiskLevel.MEDIUM

    def test_medium_upper(self):
        assert _risk_level(6) == RiskLevel.MEDIUM

    def test_low_max(self):
        assert _risk_level(3) == RiskLevel.LOW

    def test_low_min(self):
        assert _risk_level(1) == RiskLevel.LOW


class TestBuildUserMessage:
    def test_includes_required_fields(self):
        story = UserStory(
            key="PROJ-1",
            summary="Login feature",
            description="Users need to log in",
            acceptance_criteria="AC: login works",
        )
        msg = _build_user_message(story)
        assert "PROJ-1" in msg
        assert "Login feature" in msg
        assert "Users need to log in" in msg
        assert "AC: login works" in msg

    def test_omits_none_fields(self):
        story = UserStory(key="PROJ-2", summary="Minimal story")
        msg = _build_user_message(story)
        assert "None" not in msg
        assert "Description" not in msg


class TestAIAgentGenerate:
    @patch("src.ai_agent.anthropic.Anthropic")
    def test_returns_test_suite(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.input = {
            "scenarios": [
                {
                    "title": "Happy path login",
                    "gherkin": "Feature: Login\nScenario: Happy path\nGiven I am on login\nWhen I submit\nThen I am in",
                    "risk_score": 8,
                    "risk_rationale": "Critical flow",
                    "test_type": "UI",
                    "automation_candidate": True,
                    "automation_rationale": "Stable flow",
                    "testing_quadrant": "Q2",
                    "tags": ["high-risk", "ui"],
                }
            ]
        }
        mock_client.messages.create.return_value = MagicMock(
            content=[tool_use_block],
            stop_reason="tool_use",
            usage=MagicMock(input_tokens=500, output_tokens=1000),
        )

        agent = AIAgent()
        story = UserStory(key="PROJ-10", summary="User login", description="Login flow")
        suite = agent.generate_test_suite(story)

        assert suite.story_key == "PROJ-10"
        assert suite.total_test_cases == 1
        assert suite.overall_risk == RiskLevel.HIGH
        assert suite.test_cases[0].test_type == TestType.UI
        assert suite.automation_candidate_count == 1

    @patch("src.ai_agent.anthropic.Anthropic")
    def test_raises_when_no_tool_call(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[],
            stop_reason="end_turn",
            usage=MagicMock(input_tokens=100, output_tokens=10),
        )

        agent = AIAgent()
        story = UserStory(key="PROJ-99", summary="Story", description="Some description")
        with pytest.raises(ValueError, match="did not call generate_test_cases"):
            agent.generate_test_suite(story)

    @patch("src.ai_agent.anthropic.Anthropic")
    def test_raises_on_max_tokens_truncation(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[],
            stop_reason="max_tokens",
            usage=MagicMock(input_tokens=100, output_tokens=8192),
        )

        agent = AIAgent()
        story = UserStory(key="PROJ-11", summary="Big story", description="Lots of content")
        with pytest.raises(ValueError, match="truncated"):
            agent.generate_test_suite(story)

    def test_raises_on_empty_story(self):
        agent = AIAgent()
        story = UserStory(key="PROJ-00", summary="Empty story")
        with pytest.raises(ValueError, match="no description or acceptance criteria"):
            agent.generate_test_suite(story)
