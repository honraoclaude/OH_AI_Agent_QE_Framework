import logging

from jira import JIRA
from jira.exceptions import JIRAError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from src.models import UserStory

logger = logging.getLogger(__name__)

_jira_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(JIRAError),
    reraise=True,
)


class JiraClient:
    def __init__(self):
        # get_server_info=False avoids a connection attempt at instantiation time
        self._client = JIRA(
            server=settings.jira_base_url,
            basic_auth=(settings.jira_email, settings.jira_api_token),
            get_server_info=False,
        )

    @_jira_retry
    def get_story(self, issue_key: str) -> UserStory:
        issue = self._client.issue(issue_key)
        fields = issue.fields

        acceptance_criteria = self._extract_acceptance_criteria(fields)
        description = getattr(fields, "description", None) or ""
        components = [c.name for c in (getattr(fields, "components", None) or [])]
        labels = list(getattr(fields, "labels", None) or [])
        priority = getattr(getattr(fields, "priority", None), "name", None)
        story_points = getattr(fields, "customfield_10016", None)

        return UserStory(
            key=issue_key,
            summary=fields.summary,
            description=description,
            acceptance_criteria=acceptance_criteria,
            priority=priority,
            labels=labels,
            components=components,
            story_points=story_points,
        )

    @_jira_retry
    def add_comment(self, issue_key: str, body: str) -> None:
        self._client.add_comment(issue_key, body)
        logger.info("Posted comment on %s", issue_key)

    def _extract_acceptance_criteria(self, fields) -> str | None:
        value = getattr(fields, settings.jira_ac_custom_field, None)
        if value and isinstance(value, str):
            return value

        description = getattr(fields, "description", "") or ""
        if "acceptance criteria" not in description.lower():
            return None

        lines = description.splitlines()
        ac_lines: list[str] = []
        capturing = False
        for line in lines:
            if "acceptance criteria" in line.lower():
                capturing = True
                continue
            if capturing:
                if line.startswith("#") or line.startswith("h1.") or line.startswith("h2."):
                    break
                ac_lines.append(line)

        return "\n".join(ac_lines).strip() or None
