import os

# Set dummy env vars before any test module imports config.py
os.environ.setdefault("JIRA_BASE_URL", "https://test.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "test@test.com")
os.environ.setdefault("JIRA_API_TOKEN", "dummy-jira-token")
os.environ.setdefault("JIRA_WEBHOOK_SECRET", "dummy-webhook-secret")
os.environ.setdefault("PROJECT_KEY", "PROJ")
os.environ.setdefault("ZEPHYR_API_TOKEN", "dummy-zephyr-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key")
os.environ.setdefault("MAX_CONCURRENT_STORIES", "10")
os.environ.setdefault("MAX_BODY_BYTES", "1048576")
os.environ.setdefault("WEBHOOK_RATE_LIMIT", "1000/minute")  # high limit so tests never hit it
os.environ.setdefault("SHUTDOWN_TIMEOUT", "5")
os.environ.setdefault("CORS_ORIGINS", "")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("S3_BUCKET", "")
os.environ.setdefault("S3_PREFIX", "qe-agent")
