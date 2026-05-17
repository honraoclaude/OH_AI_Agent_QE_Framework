"""Tests for the FastAPI webhook server endpoints."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.webhook_server import app, _in_flight

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "dummy-webhook-secret"  # matches conftest JIRA_WEBHOOK_SECRET


def _sign(body: bytes) -> str:
    digest = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _webhook_payload(
    event: str = "jira:issue_updated",
    issue_key: str = "PROJ-123",
    status_to: str = "Ready for Test",
) -> bytes:
    data = {
        "webhookEvent": event,
        "issue": {"key": issue_key, "fields": {"summary": "Test story"}},
        "changelog": {
            "items": [{"field": "status", "fromString": "In Progress", "toString": status_to}]
        },
    }
    return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_in_flight():
    _in_flight.clear()
    yield
    _in_flight.clear()


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_valid_signature_accepted(client):
    body = _webhook_payload()
    with patch("src.webhook_server._process_story", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/jira",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": _sign(body),
            },
        )
    assert resp.status_code == 202


def test_missing_signature_rejected(client):
    body = _webhook_payload()
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_wrong_signature_rejected(client):
    body = _webhook_payload()
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401


def test_malformed_signature_header_rejected(client):
    body = _webhook_payload()
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": "notavalidformat",
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------


def test_non_target_event_ignored(client):
    body = _webhook_payload(event="jira:issue_created")
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["detail"] == "event ignored"


def test_non_target_status_transition_ignored(client):
    body = _webhook_payload(status_to="In Review")
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert "transition not targeted" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Happy path — target transition enqueues background task
# ---------------------------------------------------------------------------


def test_target_transition_accepted(client):
    body = _webhook_payload()
    with patch("src.webhook_server._process_story", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/jira",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": _sign(body),
            },
        )
    assert resp.status_code == 202
    assert "PROJ-123" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_malformed_payload_returns_422(client):
    body = b'{"webhookEvent": "jira:issue_updated"}'  # missing "issue" key
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": _sign(body),
        },
    )
    assert resp.status_code == 422


def test_invalid_issue_key_returns_422(client):
    body = _webhook_payload(issue_key="../../etc/passwd")
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": _sign(body),
        },
    )
    assert resp.status_code == 422


def test_lowercase_issue_key_returns_422(client):
    body = _webhook_payload(issue_key="proj-123")
    resp = client.post(
        "/webhook/jira",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": _sign(body),
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Body size limit
# ---------------------------------------------------------------------------


def test_oversized_body_rejected(client):
    big_body = b"x" * (1_048_576 + 1)
    resp = client.post(
        "/webhook/jira",
        content=big_body,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(big_body)),
            "X-Hub-Signature": _sign(big_body),
        },
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Concurrency guard
# ---------------------------------------------------------------------------


def test_concurrency_limit_returns_429(client):
    # Simulate max_concurrent_stories already in flight
    with patch("src.webhook_server.settings") as mock_settings:
        mock_settings.max_concurrent_stories = 0  # always at limit
        mock_settings.jira_target_status = "Ready for Test"
        mock_settings.jira_webhook_secret = _SECRET
        mock_settings.max_body_bytes = 1_048_576
        mock_settings.webhook_rate_limit = "1000/minute"

        body = _webhook_payload()
        resp = client.post(
            "/webhook/jira",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": _sign(body),
            },
        )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_health_live(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_ready_basic(client):
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert "in_flight" in body


def test_health_ready_contains_expected_checks(client):
    resp = client.get("/health/ready")
    checks = resp.json()["checks"]
    assert "jira_url" in checks
    assert "jira_token" in checks
    assert "zephyr_token" in checks
    assert "anthropic_key" in checks


def test_health_ready_deep_probe_runs(client):
    with (
        patch("src.webhook_server._jira") as mock_jira,
        patch("src.webhook_server._zephyr") as mock_zephyr,
    ):
        mock_jira._client.myself = MagicMock(return_value={"accountId": "abc"})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_zephyr._http.get = MagicMock(return_value=mock_resp)

        resp = client.get("/health/ready?deep=true")
    assert resp.status_code in (200, 503)
    checks = resp.json()["checks"]
    assert "jira_connectivity" in checks
    assert "zephyr_connectivity" in checks
