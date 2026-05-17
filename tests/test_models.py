from src.models import RiskLevel, TestCase, TestSuite, TestType, TestingQuadrant


def make_tc(
    risk_level: RiskLevel,
    quadrant: TestingQuadrant,
    automation_candidate: bool = True,
) -> TestCase:
    return TestCase(
        title="TC",
        gherkin="Given x\nWhen y\nThen z",
        risk_score=8 if risk_level == RiskLevel.HIGH else 5 if risk_level == RiskLevel.MEDIUM else 2,
        risk_level=risk_level,
        risk_rationale="test",
        test_type=TestType.UI,
        automation_candidate=automation_candidate,
        automation_rationale="test",
        testing_quadrant=quadrant,
        tags=[],
    )


class TestTestSuiteComputedFields:
    def _suite(self, test_cases: list[TestCase]) -> TestSuite:
        return TestSuite(
            story_key="PROJ-1",
            story_summary="Test story",
            generated_at="2026-05-17T00:00:00+00:00",
            test_cases=test_cases,
        )

    def test_total_test_cases(self):
        suite = self._suite([make_tc(RiskLevel.LOW, TestingQuadrant.Q1)] * 3)
        assert suite.total_test_cases == 3

    def test_total_test_cases_empty(self):
        suite = self._suite([])
        assert suite.total_test_cases == 0

    def test_automation_candidate_count(self):
        cases = [
            make_tc(RiskLevel.HIGH, TestingQuadrant.Q2, automation_candidate=True),
            make_tc(RiskLevel.LOW, TestingQuadrant.Q3, automation_candidate=False),
            make_tc(RiskLevel.MEDIUM, TestingQuadrant.Q1, automation_candidate=True),
        ]
        suite = self._suite(cases)
        assert suite.automation_candidate_count == 2

    def test_overall_risk_high_wins(self):
        cases = [
            make_tc(RiskLevel.LOW, TestingQuadrant.Q1),
            make_tc(RiskLevel.HIGH, TestingQuadrant.Q2),
        ]
        assert self._suite(cases).overall_risk == RiskLevel.HIGH

    def test_overall_risk_medium_without_high(self):
        cases = [
            make_tc(RiskLevel.LOW, TestingQuadrant.Q1),
            make_tc(RiskLevel.MEDIUM, TestingQuadrant.Q2),
        ]
        assert self._suite(cases).overall_risk == RiskLevel.MEDIUM

    def test_overall_risk_all_low(self):
        cases = [make_tc(RiskLevel.LOW, TestingQuadrant.Q3)]
        assert self._suite(cases).overall_risk == RiskLevel.LOW

    def test_overall_risk_empty_defaults_low(self):
        assert self._suite([]).overall_risk == RiskLevel.LOW

    def test_quadrant_summary_groups_correctly(self):
        cases = [
            make_tc(RiskLevel.HIGH, TestingQuadrant.Q1),
            make_tc(RiskLevel.MEDIUM, TestingQuadrant.Q2),
            make_tc(RiskLevel.LOW, TestingQuadrant.Q3),
            make_tc(RiskLevel.LOW, TestingQuadrant.Q2),
        ]
        qs = self._suite(cases).quadrant_summary
        assert len(qs.Q1) == 1
        assert len(qs.Q2) == 2
        assert len(qs.Q3) == 1
        assert len(qs.Q4) == 0

    def test_quadrant_summary_is_consistent_on_repeated_access(self):
        suite = self._suite([make_tc(RiskLevel.HIGH, TestingQuadrant.Q2)])
        assert suite.quadrant_summary.Q2 == suite.quadrant_summary.Q2
