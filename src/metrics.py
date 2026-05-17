from prometheus_client import Counter, Gauge, Histogram

stories_total = Counter(
    "qe_stories_processed_total",
    "Stories processed by the AI QE Agent",
    ["status"],  # "success" | "error"
)

generation_seconds = Histogram(
    "qe_generation_duration_seconds",
    "End-to-end wall time from story fetch to Jira comment posted",
)

tokens_total = Counter(
    "qe_token_usage_total",
    "Claude API tokens consumed",
    ["token_type"],  # "input" | "output"
)

in_flight_gauge = Gauge(
    "qe_in_flight_stories",
    "Number of stories currently being processed",
)
