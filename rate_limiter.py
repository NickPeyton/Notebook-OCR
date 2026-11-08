"""Model cascade driven by Google's own rate-limit (429) errors.

Free-tier limits are not published in a machine-readable form and change without
notice, so no limits are configured locally. Instead, each 429 says which quota
was hit (per-minute or per-day) and how long to wait. Rejected requests do not
use up quota, so learning limits this way costs nothing.
"""
import json
import logging
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MODEL_CONFIG_PATH = Path("model_config.json")
RATE_USAGE_PATH = Path("rate_usage.json")

PACIFIC = ZoneInfo("America/Los_Angeles")  # Gemini daily quotas reset at midnight Pacific
RESET_MARGIN = timedelta(minutes=5)  # wait a little past midnight in case the reset is late
DEFAULT_COOLDOWN = 60.0  # seconds, used when a 429 gives no retry delay
MAX_SLEEP = 60.0  # seconds; longest single sleep while waiting for a model


def _load_models() -> list[str]:
    """Model names in priority order (first = preferred)."""
    return json.loads(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))


def _load_usage() -> dict:
    if RATE_USAGE_PATH.exists():
        return json.loads(RATE_USAGE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_usage(usage: dict):
    tmp = RATE_USAGE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(usage, indent=2), encoding="utf-8")
    tmp.replace(RATE_USAGE_PATH)


def _next_daily_reset() -> float:
    """Unix timestamp shortly after the next daily quota reset (midnight Pacific)."""
    tomorrow = (datetime.now(PACIFIC) + timedelta(days=1)).date()
    return (datetime.combine(tomorrow, dtime.min, tzinfo=PACIFIC) + RESET_MARGIN).timestamp()


def _parse_quota_error(details) -> tuple[bool, list[str], float | None]:
    """Read the details of a 429 response.

    Returns (is_daily, limits_hit, retry_seconds):
      is_daily     -- True if a per-day quota was exceeded
      limits_hit   -- e.g. ["GenerateRequestsPerDayPerProjectPerModel-FreeTier=20"], for the log
      retry_seconds -- Google's suggested wait, or None
    Anything missing or in an unexpected format is simply left out.
    """
    is_daily, limits_hit, retry_seconds = False, [], None
    try:
        items = details.get("error", {}).get("details", [])
    except AttributeError:
        return is_daily, limits_hit, retry_seconds

    for item in items:
        for violation in item.get("violations", []):
            quota_id = violation.get("quotaId", "")
            if "PerDay" in quota_id:
                is_daily = True
            limits_hit.append(f"{quota_id}={violation.get('quotaValue')}")
        if "retryDelay" in item:
            try:
                retry_seconds = float(str(item["retryDelay"]).rstrip("s"))
            except ValueError:
                pass
    return is_daily, limits_hit, retry_seconds


def select_model() -> str:
    """Pick the highest-priority model that is not cooling down after a 429.

    If every model is cooling down, waits until the first one becomes available —
    up to the next daily reset if every model has hit its daily limit (e.g. while
    working through a large backlog). Never gives up.
    """
    models = _load_models()
    logged_until = None

    while True:
        usage = _load_usage()
        now = time.time()

        for model in models:
            if now >= usage.get(model, {}).get("cooldown_until", 0.0):
                logger.info(f"Selected model: {model}")
                return model

        available_at = min(usage[model]["cooldown_until"] for model in models)
        if available_at != logged_until:
            until = datetime.fromtimestamp(available_at, PACIFIC).strftime("%Y-%m-%d %H:%M %Z")
            logger.info(f"All models rate-limited, waiting until {until}")
            logged_until = available_at

        # Sleep in short steps and re-check the clock, so the wait stays correct
        # if the computer sleeps in the meantime
        time.sleep(min(available_at - now + 1.0, MAX_SLEEP))


def record_rate_limit(model: str, error_details):
    """Put a model on cooldown after a 429, for as long as the error says."""
    is_daily, limits_hit, retry_seconds = _parse_quota_error(error_details)

    if is_daily:
        cooldown_until = _next_daily_reset()
    else:
        cooldown_until = time.time() + (retry_seconds or DEFAULT_COOLDOWN)

    usage = _load_usage()
    usage[model] = {
        "cooldown_until": cooldown_until,
        "daily_limit_hit": is_daily,
        "limits_hit": limits_hit,
        "recorded_at": datetime.now(PACIFIC).isoformat(timespec="seconds"),
    }
    _save_usage(usage)

    until = datetime.fromtimestamp(cooldown_until, PACIFIC).strftime("%Y-%m-%d %H:%M %Z")
    kind = "daily limit" if is_daily else "per-minute limit"
    logger.warning(
        f"{model}: {kind} reached ({', '.join(limits_hit) or 'no quota details'}); "
        f"skipping until {until}"
    )
