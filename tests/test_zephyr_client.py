from unittest.mock import MagicMock, patch


from src.models import RiskLevel, TestCase, TestType, TestingQuadrant
from src.zephyr_client import ZephyrClient


def make_test_case() -> TestCase:
    return TestCase(
        title="Successful login",
        gherkin="Given I am on login\nWhen I submit valid creds\nThen I see dashboard",
        risk_score=8,
        risk_level=RiskLevel.HIGH,
        risk_rationale="Core journey",
        test_type=TestType.UI,
        automation_candidate=True,
        automation_rationale="Stable, high frequency",
        testing_quadrant=TestingQuadrant.Q2,
        tags=["high-risk", "ui", "automate"],
    )


class TestCreateTestCase:
    @patch("src.zephyr_client.httpx.Client")
    def test_returns_test_key(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "PROJ-T42"}
        mock_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.post.return_value = mock_response
        mock_client_cls.return_value = mock_http

        client = ZephyrClient()
        key = client.create_test_case("PROJ", "PROJ-1", make_test_case(), folder_id=10)

        assert key == "PROJ-T42"
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["testScript"]["type"] == "BDD"
        assert payload["priorityName"] == "High"


class TestGetOrCreateFolder:
    @patch("src.zephyr_client.httpx.Client")
    def test_returns_existing_folder(self, mock_client_cls):
        list_response = MagicMock()
        list_response.json.return_value = {
            "values": [{"id": 99, "name": "AI Generated — PROJ-1"}]
        }
        list_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = list_response
        mock_client_cls.return_value = mock_http

        client = ZephyrClient()
        folder_id = client.get_or_create_folder("PROJ", "PROJ-1")
        assert folder_id == 99

    @patch("src.zephyr_client.httpx.Client")
    def test_creates_new_folder_when_absent(self, mock_client_cls):
        list_response = MagicMock()
        list_response.json.return_value = {"values": []}
        list_response.raise_for_status = MagicMock()

        create_response = MagicMock()
        create_response.json.return_value = {"id": 55}
        create_response.raise_for_status = MagicMock()

        mock_http = MagicMock()
        mock_http.__enter__ = MagicMock(return_value=mock_http)
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.get.return_value = list_response
        mock_http.post.return_value = create_response
        mock_client_cls.return_value = mock_http

        client = ZephyrClient()
        folder_id = client.get_or_create_folder("PROJ", "PROJ-2")
        assert folder_id == 55
