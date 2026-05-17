# AI QE Agent

Automated BDD test case generation for Jira User Stories using Claude AI, with direct write-back to Zephyr Scale.

## How it works

1. A Jira webhook fires when a story transitions to **Ready for Test**.
2. The agent fetches the story (description + acceptance criteria) from Jira Cloud.
3. Claude AI generates BDD Gherkin test cases, tagging each with:
   - Risk score (1–10) and level (LOW / MEDIUM / HIGH)
   - Test type (UI / INTEGRATION / UNIT)
   - Automation candidacy + rationale
   - Brian Marick Testing Quadrant (Q1–Q4)
4. Test cases are written to Zephyr Scale, linked to the originating story.
5. A summary comment is posted on the Jira issue.
6. `.feature` and `_report.json` files are written locally (or to S3).

---

## Prerequisites

- Python 3.13+
- A Jira Cloud account with webhook capability
- [Zephyr Scale](https://smartbear.com/test-management/zephyr-scale/) installed in your Jira project
- An [Anthropic API key](https://console.anthropic.com/)
- Docker (for production deployment)

---

## Quickstart

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd OH_AI_AGENT_QE_FRAMEWORK
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@yourcompany.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_WEBHOOK_SECRET=a-random-secret-string
ZEPHYR_API_TOKEN=your-zephyr-api-token
ANTHROPIC_API_KEY=your-anthropic-api-key
```

### 3. Run the server

```bash
uvicorn src.webhook_server:app --host 0.0.0.0 --port 8000 --reload
```

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `JIRA_BASE_URL` | Yes | — | Jira Cloud base URL (must be `https://`) |
| `JIRA_EMAIL` | Yes | — | Email used for Jira API auth |
| `JIRA_API_TOKEN` | Yes | — | Jira API token |
| `JIRA_WEBHOOK_SECRET` | Yes | — | Shared secret for HMAC-SHA256 signature verification |
| `JIRA_TARGET_STATUS` | No | `Ready for Test` | Status transition that triggers generation |
| `JIRA_AC_CUSTOM_FIELD` | No | `customfield_10034` | Custom field ID containing acceptance criteria |
| `PROJECT_KEY` | No | *(auto-derived)* | Zephyr project key; leave empty to derive from issue key prefix |
| `ZEPHYR_API_TOKEN` | Yes | — | Zephyr Scale API token |
| `ZEPHYR_BASE_URL` | No | `https://api.zephyrscale.smartbear.com/v2` | Zephyr Scale API base URL |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-6` | Claude model ID |
| `CLAUDE_MAX_TOKENS` | No | `8192` | Max tokens for Claude response |
| `MAX_CONCURRENT_STORIES` | No | `10` | Maximum stories processed simultaneously |
| `MAX_BODY_BYTES` | No | `1048576` | Maximum webhook body size (bytes) |
| `WEBHOOK_RATE_LIMIT` | No | `60/minute` | Per-IP rate limit on `/webhook/jira` |
| `SHUTDOWN_TIMEOUT` | No | `30` | Seconds to wait for in-flight tasks on shutdown |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_FORMAT` | No | `text` | `text` or `json` (use `json` for cloud log aggregation) |
| `OUTPUT_DIR` | No | `output` | Local directory for `.feature` and `_report.json` files |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `S3_BUCKET` | No | — | S3 bucket name (required when `STORAGE_BACKEND=s3`) |
| `S3_PREFIX` | No | `qe-agent` | S3 key prefix |
| `CORS_ORIGINS` | No | *(block all)* | Comma-separated allowed CORS origins |

---

## Jira webhook setup

1. Go to **Jira Settings → System → WebHooks**.
2. Click **Create a WebHook**.
3. Set URL to `https://your-agent-host/webhook/jira`.
4. Under **Secret**, enter the same value as `JIRA_WEBHOOK_SECRET`.
5. Under **Events**, select **Issue → updated**.
6. Save. Jira will now POST to the agent on every issue update.

---

## Zephyr Scale setup

1. Generate an API token at **Zephyr Scale → API Access Tokens**.
2. Set `ZEPHYR_API_TOKEN` in your `.env`.
3. The agent will automatically create a folder named `AI Generated — <ISSUE_KEY>` under your project's test cases and link each generated test case to the originating story.

---

## Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Generate an HTML report:

```bash
pytest tests/ -v --html=report.html --self-contained-html
```

---

## Docker deployment

### Build and run

```bash
docker build -t ai-qe-agent .
docker run --env-file .env -p 8000:8000 ai-qe-agent
```

### Docker Compose

```bash
docker compose up -d
```

Output files are written to `./output/` on the host via a volume mount.

### Health checks

- `GET /health/live` — liveness probe (process running)
- `GET /health/ready` — readiness probe (all dependencies configured)
- `GET /health/ready?deep=true` — also probes Jira and Zephyr connectivity

---

## Observability

Prometheus metrics are exposed at `GET /metrics`:

| Metric | Type | Description |
|---|---|---|
| `qe_stories_processed_total` | Counter | Stories processed, labelled `status=success\|error` |
| `qe_generation_duration_seconds` | Histogram | End-to-end wall time per story |
| `qe_token_usage_total` | Counter | Claude API tokens consumed, labelled `token_type=input\|output` |
| `qe_in_flight_stories` | Gauge | Stories currently being processed |

Set `LOG_FORMAT=json` and ship stdout to your preferred log aggregator (CloudWatch, ELK, Datadog).

---

## Secrets management

| Platform | Recommended approach |
|---|---|
| Single VM | `.env` file (never commit to git) |
| AWS | Secrets Manager + IAM role; no `.env` needed |
| Azure | Key Vault + Managed Identity |
| Kubernetes | Native secrets mounted as environment variables |

---

## Troubleshooting

**`ValidationError` on startup** — One or more required env vars are missing. Check that `.env` contains all required fields listed above.

**`401 Invalid webhook signature`** — `JIRA_WEBHOOK_SECRET` does not match the secret configured in Jira. Regenerate and update both sides.

**`422 Invalid issue key format`** — The incoming webhook contained a non-standard issue key. Check the Jira project key format (`[A-Z][A-Z0-9]+-[0-9]+`).

**`429 Too busy`** — More than `MAX_CONCURRENT_STORIES` stories are processing simultaneously. Increase the limit or let the queue drain and retry.

**Story has no description or acceptance criteria** — The agent requires at least one of these fields to generate meaningful tests. Populate the Jira story before transitioning to Ready for Test.

**Zephyr folder not found** — Ensure the Zephyr project key matches the Jira project. Set `PROJECT_KEY` explicitly if they differ.
