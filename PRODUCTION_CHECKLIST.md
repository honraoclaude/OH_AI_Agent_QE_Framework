# Production Deployment Checklist

## 1. Gather Credentials

- [ X] Get **Jira API token** — `https://id.atlassian.com` → Security → API tokens
- [ X] Get **Zephyr Scale API token** — Jira → Zephyr Scale → Settings → API Access Tokens
- [X ] Get **Anthropic API key** — `https://console.anthropic.com` → API Keys
- [ X] Generate **webhook secret**:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

---

## 2. Provision Infrastructure

- [ ] Provision a server with a **public HTTPS URL**
  - Easiest: AWS App Runner / Azure Container Apps / Google Cloud Run (HTTPS out of the box)
  - VM option: DigitalOcean or AWS Lightsail Ubuntu + Nginx + Let's Encrypt
  - Kubernetes: deploy image with Ingress + cert-manager

---

## 3. Configure Environment

- [ ] Create `.env` on the server (copy from `.env.example` and fill in real values):
  ```dotenv
  JIRA_BASE_URL=https://yourcompany.atlassian.net
  JIRA_EMAIL=you@yourcompany.com
  JIRA_API_TOKEN=<from step 1>
  JIRA_WEBHOOK_SECRET=<random secret from step 1>
  JIRA_TARGET_STATUS=Ready for Test
  ZEPHYR_API_TOKEN=<from step 1>
  ANTHROPIC_API_KEY=<from step 1>
  PROJECT_KEY=SCRUM
  LOG_FORMAT=json
  ```

---

## 4. Deploy

- [ ] Clone repo and deploy:
  ```bash
  git clone https://github.com/honraoclaude/OH_AI_Agent_QE_Framework.git
  cd OH_AI_Agent_QE_Framework
  cp .env.example .env   # then fill in real values
  docker compose up -d
  ```
- [ ] Verify all health checks pass:
  ```bash
  curl https://your-domain.com/health/ready?deep=true
  ```
  All checks must return `"ok"` before wiring Jira.

---

## 5. Register Jira Webhook

- [ ] Go to **Jira Settings → System → WebHooks → Create a WebHook**
  - URL: `https://your-domain.com/webhook/jira`
  - Secret: same value as `JIRA_WEBHOOK_SECRET`
  - Events: **Issue → updated**
  - JQL filter (recommended): `project = SCRUM AND issuetype = Story`
  - Save

---

## 6. Smoke Test

- [ ] Open a Jira story with a description or acceptance criteria
- [ ] Transition it to **Ready for Test**
- [ ] Verify within ~30 seconds:
  - New test cases appear in Zephyr Scale under `AI Generated — <ISSUE-KEY>` folder
  - A summary comment is posted on the Jira story
  - A `.feature` file is written to `output/`

---

## 7. Post-Launch Hardening

- [ ] Set **Anthropic monthly spend limit** at `https://console.anthropic.com` (prevents runaway costs)
- [ ] Refine **Jira webhook JQL filter**: `issuetype = Story AND "Story Points" > 0`
- [ ] Wire **`/metrics`** to Grafana or Datadog — alert on `qe_stories_processed_total{status="error"}`
- [ ] Configure **log shipping**: set `LOG_FORMAT=json` and pipe stdout to CloudWatch / ELK / Datadog
