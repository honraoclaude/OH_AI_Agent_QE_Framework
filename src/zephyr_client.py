import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings
from src.models import RiskLevel, TestCase

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    RiskLevel.HIGH: "High",
    RiskLevel.MEDIUM: "Medium",
    RiskLevel.LOW: "Low",
}

_PAGE_SIZE = 100


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.RequestError)


_zephyr_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


class ZephyrClient:
    def __init__(self):
        self._base = settings.zephyr_base_url.rstrip("/")
        self._http = httpx.Client(
            headers={
                "Authorization": f"Bearer {settings.zephyr_api_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    def close(self) -> None:
        self._http.close()

    @_zephyr_retry
    def create_test_case(
        self,
        project_key: str,
        story_key: str,
        test_case: TestCase,
        folder_id: int | None = None,
    ) -> str:
        payload = {
            "projectKey": project_key,
            "name": test_case.title,
            "statusName": "Draft",
            "priorityName": _PRIORITY_MAP[test_case.risk_level],
            "labels": test_case.tags,
            "testScript": {
                "type": "BDD",
                "text": test_case.gherkin,
            },
        }
        if folder_id:
            payload["folderId"] = folder_id

        response = self._http.post(f"{self._base}/testcases", json=payload)
        response.raise_for_status()
        test_key: str = response.json()["key"]
        logger.info("Created Zephyr test case %s for story %s", test_key, story_key)
        return test_key

    @_zephyr_retry
    def link_test_to_story(self, test_key: str, issue_key: str) -> None:
        payload = {"issueKey": issue_key, "testCaseKey": test_key}
        response = self._http.post(f"{self._base}/issuelinks", json=payload)
        response.raise_for_status()
        logger.info("Linked %s to Jira issue %s", test_key, issue_key)

    def get_or_create_folder(self, project_key: str, story_key: str) -> int:
        folder_name = f"AI Generated — {story_key}"
        start_at = 0

        while True:
            resp = self._http.get(
                f"{self._base}/folders",
                params={
                    "projectKey": project_key,
                    "folderType": "TEST_CASE",
                    "startAt": start_at,
                    "maxResults": _PAGE_SIZE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            for folder in data.get("values", []):
                if folder.get("name") == folder_name:
                    return folder["id"]
            if data.get("isLast", True):
                break
            start_at += _PAGE_SIZE

        create_resp = self._http.post(
            f"{self._base}/folders",
            json={
                "name": folder_name,
                "projectKey": project_key,
                "folderType": "TEST_CASE",
            },
        )
        create_resp.raise_for_status()
        folder_id: int = create_resp.json()["id"]
        logger.info("Created Zephyr folder '%s' (id=%d)", folder_name, folder_id)
        return folder_id
