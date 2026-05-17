from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Jira Cloud
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_webhook_secret: str
    jira_target_status: str = "Ready for Test"
    jira_ac_custom_field: str = "customfield_10034"

    # Project — leave empty to auto-derive from incoming issue key prefix (multi-project support)
    project_key: str = ""

    # Zephyr Scale
    zephyr_api_token: str
    zephyr_base_url: str = "https://api.zephyrscale.smartbear.com/v2"

    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 8192

    # Server behaviour
    max_concurrent_stories: int = 10
    max_body_bytes: int = 1_048_576       # 1 MB
    webhook_rate_limit: str = "60/minute"
    shutdown_timeout: int = 30            # seconds to wait for in-flight tasks on shutdown

    # Observability
    log_level: str = "INFO"
    log_format: str = "text"             # "text" or "json"

    # Output
    output_dir: str = "output"
    storage_backend: str = "local"       # "local" or "s3"
    s3_bucket: str = ""
    s3_prefix: str = "qe-agent"

    # Security
    cors_origins: str = ""               # comma-separated allowed origins; empty = block all cross-origin


settings = Settings()
