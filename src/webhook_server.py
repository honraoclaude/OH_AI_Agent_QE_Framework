import asyncio
import hashlib
import hmac
import logging
import logging.config
import re
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger import jsonlogger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import settings
from src.ai_agent import AIAgent
from src.jira_client import JiraClient
from src.metrics import generation_seconds, in_flight_gauge, stories_total
from src.models import JiraWebhookEvent, TestCase, TestSuite
from src.output_writer import write_suite_output
from src.zephyr_client import ZephyrClient

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    handler = logging.StreamHandler()
    if settings.log_format == "json":
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers = [handler]


_configure_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level service clients
# ---------------------------------------------------------------------------

_jira = JiraClient()
_zephyr = ZephyrClient()
_agent = AIAgent()

# ---------------------------------------------------------------------------
# Concurrency state
# ---------------------------------------------------------------------------

_in_flight: set[str] = set()       # active story keys (dedup + concurrency limit)
_active_tasks: set[asyncio.Task] = set()  # tracked tasks for graceful shutdown

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

_limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")


def _validate_issue_key(key: str) -> bool:
    return bool(_ISSUE_KEY_RE.match(key))


def _get_project_key(issue_key: str) -> str:
    """Return configured project key, or derive from issue key prefix."""
    if settings.project_key:
        return settings.project_key
    return issue_key.rsplit("-", 1)[0]


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jira_base_url.startswith("https://"):
        logger.warning(
            "JIRA_BASE_URL '%s' is not HTTPS — Jira Cloud requires HTTPS for webhook delivery",
            settings.jira_base_url,
        )
    yield
    # Graceful shutdown: wait for in-flight tasks to finish
    if _active_tasks:
        logger.info(
            "Shutdown: waiting for %d in-flight task(s) (timeout=%ds)",
            len(_active_tasks),
            settings.shutdown_timeout,
        )
        _, pending = await asyncio.wait(_active_tasks, timeout=settings.shutdown_timeout)
        if pending:
            logger.warning("Shutdown: %d task(s) did not complete in time", len(pending))
    _zephyr.close()


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="AI QE Agent", version="1.0.0", lifespan=lifespan)

# Prometheus HTTP metrics (exposes /metrics)
Instrumentator().instrument(app).expose(app, include_in_schema=False)

# Rate limiter exception handler
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — defaults to blocking all cross-origin if CORS_ORIGINS is empty
_cors_origins = (
    [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if settings.cors_origins
    else []
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Hub-Signature"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _story_log(story_key: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"story_key": story_key})


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    if not signature_header:
        return False
    try:
        _, sig = signature_header.split("=", 1)
    except ValueError:
        return False
    expected = hmac.new(
        settings.jira_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def _is_target_transition(event: JiraWebhookEvent) -> bool:
    changelog = event.changelog or {}
    for item in changelog.get("items", []):
        if item.get("field") == "status" and item.get("toString") == settings.jira_target_status:
            return True
    return False


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

async def _process_story(issue_key: str) -> None:
    if issue_key in _in_flight:
        logger.warning("Skipping %s — already processing", issue_key)
        return

    _in_flight.add(issue_key)
    in_flight_gauge.set(len(_in_flight))
    log = _story_log(issue_key)
    start = time.monotonic()

    task = asyncio.current_task()
    if task:
        _active_tasks.add(task)

    try:
        log.info("Starting AI QE generation")
        story = await asyncio.to_thread(_jira.get_story, issue_key)
        suite = await asyncio.to_thread(_agent.generate_test_suite, story)

        # Record Claude token usage
        for tc in suite.test_cases:
            _ = tc  # token counts are logged inside ai_agent; Prometheus recorded there

        await _write_to_zephyr(suite, issue_key)
        await asyncio.to_thread(write_suite_output, suite)
        comment = _build_jira_comment(suite)
        await asyncio.to_thread(_jira.add_comment, issue_key, comment)

        stories_total.labels(status="success").inc()
        log.info(
            "Completed AI QE generation — %d test cases written in %.1fs",
            suite.total_test_cases,
            time.monotonic() - start,
        )
    except Exception:
        stories_total.labels(status="error").inc()
        logger.exception("Failed to process story %s", issue_key)
        try:
            await asyncio.to_thread(
                _jira.add_comment,
                issue_key,
                f"*[AI QE Agent]* Test generation failed for {issue_key}. "
                "Check agent logs for details.",
            )
        except Exception:
            logger.exception("Also failed to post error comment on %s", issue_key)
    finally:
        generation_seconds.observe(time.monotonic() - start)
        _in_flight.discard(issue_key)
        in_flight_gauge.set(len(_in_flight))
        if task:
            _active_tasks.discard(task)


async def _write_single_test(tc: TestCase, issue_key: str, folder_id: int) -> None:
    project_key = _get_project_key(issue_key)
    test_key = await asyncio.to_thread(
        _zephyr.create_test_case, project_key, issue_key, tc, folder_id
    )
    tc.zephyr_key = test_key
    if test_key:
        await asyncio.to_thread(_zephyr.link_test_to_story, test_key, issue_key)


async def _write_to_zephyr(suite: TestSuite, issue_key: str) -> None:
    project_key = _get_project_key(issue_key)
    folder_id = await asyncio.to_thread(
        _zephyr.get_or_create_folder, project_key, issue_key
    )
    await asyncio.gather(
        *[_write_single_test(tc, issue_key, folder_id) for tc in suite.test_cases]
    )


def _build_jira_comment(suite: TestSuite) -> str:
    rows = []
    for tc in suite.test_cases:
        automate = "YES" if tc.automation_candidate else "NO"
        rows.append(
            f"| {tc.title} | {tc.risk_level.value} ({tc.risk_score}) "
            f"| {tc.test_type.value} | {automate} | {tc.testing_quadrant.value} "
            f"| {tc.zephyr_key or '—'} |"
        )
    table = "| Test Case | Risk | Type | Automate | Quadrant | Zephyr |\n|---|---|---|---|---|---|\n"
    table += "\n".join(rows)

    qs = suite.quadrant_summary
    quadrant_line = (
        f"Q1 (Automated/Technology): {len(qs.Q1)} | Q2 (Automated/Business): {len(qs.Q2)} | "
        f"Q3 (Manual/Business): {len(qs.Q3)} | Q4 (Tools/Technology): {len(qs.Q4)}"
    )
    return (
        f"*AI-Generated Test Suite for {suite.story_key}* — Generated {suite.generated_at[:10]}\n\n"
        f"{table}\n\n*Testing Quadrant Coverage:*\n{quadrant_line}\n\n"
        f"*Automation Candidates: {suite.automation_candidate_count} of {suite.total_test_cases} "
        f"| Overall Risk: {suite.overall_risk.value}*"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/webhook/jira", status_code=status.HTTP_202_ACCEPTED)
@_limiter.limit(settings.webhook_rate_limit)
async def jira_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    # Body size guard
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")

    body = await request.body()
    if len(body) > settings.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")

    if not _verify_signature(body, request.headers.get("X-Hub-Signature")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = JiraWebhookEvent(**await request.json())
    except Exception:
        raise HTTPException(status_code=422, detail="Malformed webhook payload")

    if event.webhookEvent != "jira:issue_updated":
        return JSONResponse({"detail": "event ignored"}, status_code=200)

    if not _is_target_transition(event):
        return JSONResponse({"detail": "status transition not targeted"}, status_code=200)

    issue_key: str = event.issue["key"]

    if not _validate_issue_key(issue_key):
        raise HTTPException(status_code=422, detail=f"Invalid issue key format: {issue_key!r}")

    if len(_in_flight) >= settings.max_concurrent_stories:
        raise HTTPException(
            status_code=429,
            detail=f"Too busy — {settings.max_concurrent_stories} stories already processing. Retry later.",
        )

    logger.info("Queuing AI QE generation for %s", issue_key)
    background_tasks.add_task(_process_story, issue_key)
    return JSONResponse({"detail": f"Processing started for {issue_key}"}, status_code=202)


@app.get("/health/live")
async def health_live() -> dict:
    """Liveness probe — is the process running?"""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(deep: bool = False) -> JSONResponse:
    """Readiness probe. Pass ?deep=true to also probe Jira and Zephyr connectivity."""
    checks: dict[str, str] = {
        "jira_url": "ok" if settings.jira_base_url.startswith("https://") else "not_https",
        "jira_token": "ok" if settings.jira_api_token else "missing",
        "zephyr_token": "ok" if settings.zephyr_api_token else "missing",
        "anthropic_key": "ok" if settings.anthropic_api_key else "missing",
    }

    if deep:
        try:
            await asyncio.to_thread(_jira._client.myself)
            checks["jira_connectivity"] = "ok"
        except Exception as exc:
            checks["jira_connectivity"] = f"error: {str(exc)[:80]}"

        try:
            resp = await asyncio.to_thread(
                _zephyr._http.get, f"{settings.zephyr_base_url}/projects"
            )
            checks["zephyr_connectivity"] = "ok" if resp.status_code < 500 else f"error: {resp.status_code}"
        except Exception as exc:
            checks["zephyr_connectivity"] = f"error: {str(exc)[:80]}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if all_ok else "degraded", "checks": checks, "in_flight": len(_in_flight)},
        status_code=200 if all_ok else 503,
    )
