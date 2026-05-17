"""
Load test for the AI QE Agent webhook server.

Usage:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
        --users 50 --spawn-rate 5 --run-time 60s --headless

Set WEBHOOK_SECRET env var to match the server's JIRA_WEBHOOK_SECRET.
"""

import hashlib
import hmac
import json
import os

from locust import HttpUser, between, task

_SECRET = os.getenv("WEBHOOK_SECRET", "dummy-webhook-secret")
_STORY_COUNTER = 0


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _make_payload(story_num: int) -> bytes:
    return json.dumps({
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": f"LOAD-{story_num}",
            "fields": {"summary": f"Load test story {story_num}"},
        },
        "changelog": {
            "items": [{"field": "status", "fromString": "In Progress", "toString": "Ready for Test"}]
        },
    }).encode()


class WebhookUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        global _STORY_COUNTER
        _STORY_COUNTER += 1
        self._story_num = _STORY_COUNTER

    @task(10)
    def post_webhook(self):
        body = _make_payload(self._story_num)
        self.client.post(
            "/webhook/jira",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": _sign(body),
            },
            name="/webhook/jira",
        )

    @task(3)
    def health_live(self):
        self.client.get("/health/live", name="/health/live")

    @task(1)
    def health_ready(self):
        self.client.get("/health/ready", name="/health/ready")
