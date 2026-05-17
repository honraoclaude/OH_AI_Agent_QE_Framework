import json
from pathlib import Path


from src.models import RiskLevel, TestCase, TestSuite, TestType, TestingQuadrant
from src.output_writer import write_suite_output


def make_suite(tmp_path: Path) -> TestSuite:
    tc1 = TestCase(
        title="Successful login with valid credentials",
        gherkin=(
            "Scenario: Successful login with valid credentials\n"
            "  Given I am on the login page\n"
            "  When I enter username 'user@example.com' and password 'Passw0rd!'\n"
            "  And I click Login\n"
            "  Then I am redirected to the dashboard\n"
            "  And I see 'Welcome, user'"
        ),
        risk_score=8,
        risk_level=RiskLevel.HIGH,
        risk_rationale="Core user journey; authentication failure blocks all access",
        test_type=TestType.UI,
        automation_candidate=True,
        automation_rationale="Stable UI flow, critical regression candidate",
        testing_quadrant=TestingQuadrant.Q2,
        tags=["high-risk", "ui", "automate", "regression"],
    )
    tc2 = TestCase(
        title="Login blocked after 5 failed attempts",
        gherkin=(
            "Scenario: Login blocked after 5 failed attempts\n"
            "  Given I have failed to log in 4 times\n"
            "  When I submit invalid credentials a 5th time\n"
            "  Then my account is locked for 15 minutes\n"
            "  And I see 'Account temporarily locked'"
        ),
        risk_score=7,
        risk_level=RiskLevel.HIGH,
        risk_rationale="Security control — brute-force protection",
        test_type=TestType.INTEGRATION,
        automation_candidate=True,
        automation_rationale="Deterministic lockout logic, easy to automate",
        testing_quadrant=TestingQuadrant.Q1,
        tags=["high-risk", "integration", "automate", "security"],
    )
    tc3 = TestCase(
        title="Usability of error messages explored",
        gherkin=(
            "Scenario: Usability of error messages explored\n"
            "  Given I am on the login page\n"
            "  When I submit an empty form\n"
            "  Then I see validation messages for each empty field"
        ),
        risk_score=3,
        risk_level=RiskLevel.LOW,
        risk_rationale="UI copy only — no data risk",
        test_type=TestType.UI,
        automation_candidate=False,
        automation_rationale="Requires human judgement on message clarity",
        testing_quadrant=TestingQuadrant.Q3,
        tags=["low-risk", "ui", "manual", "exploratory"],
    )
    return TestSuite(
        story_key="PROJ-42",
        story_summary="As a registered user I want to log in so that I can access my account",
        generated_at="2026-05-17T10:00:00+00:00",
        test_cases=[tc1, tc2, tc3],
    )


class TestWriteSuiteOutput:
    def test_creates_output_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        out_dir = write_suite_output(suite)
        assert out_dir.exists()
        assert out_dir.name == "PROJ-42"

    def test_feature_file_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        feature_file = tmp_path / "PROJ-42" / "PROJ-42.feature"
        assert feature_file.exists()

    def test_json_report_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        json_file = tmp_path / "PROJ-42" / "PROJ-42_report.json"
        assert json_file.exists()

    def test_feature_file_has_feature_declaration(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        content = (tmp_path / "PROJ-42" / "PROJ-42.feature").read_text()
        assert "Feature: As a registered user I want to log in" in content

    def test_feature_file_has_all_scenarios(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        content = (tmp_path / "PROJ-42" / "PROJ-42.feature").read_text()
        assert "TC-001" in content
        assert "TC-002" in content
        assert "TC-003" in content
        assert "Successful login with valid credentials" in content
        assert "Login blocked after 5 failed attempts" in content

    def test_feature_file_has_metadata_comments(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        content = (tmp_path / "PROJ-42" / "PROJ-42.feature").read_text()
        assert "Overall Risk: HIGH" in content
        assert "Automation Candidates: 2/3" in content
        assert "Risk Rationale:" in content
        assert "Automation Rationale:" in content

    def test_feature_file_has_tags(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        content = (tmp_path / "PROJ-42" / "PROJ-42.feature").read_text()
        assert "@high-risk" in content
        assert "@automate" in content
        assert "@manual" in content

    def test_json_report_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        raw = (tmp_path / "PROJ-42" / "PROJ-42_report.json").read_text()
        data = json.loads(raw)
        assert data["story_key"] == "PROJ-42"
        assert data["total_test_cases"] == 3
        assert data["overall_risk"] == "HIGH"
        assert data["automation_candidate_count"] == 2
        assert len(data["test_cases"]) == 3

    def test_json_report_quadrant_summary(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        data = json.loads((tmp_path / "PROJ-42" / "PROJ-42_report.json").read_text())
        qs = data["quadrant_summary"]
        assert len(qs["Q1"]) == 1
        assert len(qs["Q2"]) == 1
        assert len(qs["Q3"]) == 1
        assert len(qs["Q4"]) == 0

    def test_idempotent_overwrite(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.output_writer.settings.output_dir", str(tmp_path))
        suite = make_suite(tmp_path)
        write_suite_output(suite)
        write_suite_output(suite)  # second call must not raise
        assert (tmp_path / "PROJ-42" / "PROJ-42.feature").exists()
