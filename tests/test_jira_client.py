from unittest.mock import MagicMock, patch


from src.jira_client import JiraClient


class TestGetStory:
    @patch("src.jira_client.JIRA")
    def test_returns_user_story(self, mock_jira_cls):
        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira

        fields = MagicMock()
        fields.summary = "Reset password"
        fields.description = "Users can reset their password"
        fields.components = []
        fields.labels = ["auth"]
        fields.priority = MagicMock(name="High")
        fields.priority.name = "High"
        fields.story_points = 3
        mock_jira.issue.return_value = MagicMock(fields=fields)

        client = JiraClient()
        story = client.get_story("PROJ-5")

        assert story.key == "PROJ-5"
        assert story.summary == "Reset password"
        assert "auth" in story.labels
        assert story.priority == "High"

    @patch("src.jira_client.JIRA")
    def test_extracts_acceptance_criteria_from_description(self, mock_jira_cls):
        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira

        fields = MagicMock()
        fields.summary = "Test story"
        fields.description = (
            "Some description text.\n\nAcceptance Criteria\n- AC1: Do X\n- AC2: Do Y"
        )
        fields.components = []
        fields.labels = []
        fields.priority = None
        fields.story_points = None
        mock_jira.issue.return_value = MagicMock(fields=fields)

        client = JiraClient()
        story = client.get_story("PROJ-6")
        assert story.acceptance_criteria is not None
        assert "AC1" in story.acceptance_criteria


class TestAddComment:
    @patch("src.jira_client.JIRA")
    def test_calls_jira_add_comment(self, mock_jira_cls):
        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira

        client = JiraClient()
        client.add_comment("PROJ-7", "Test comment body")
        mock_jira.add_comment.assert_called_once_with("PROJ-7", "Test comment body")
