import logging
import os
import re
import smtplib
import time
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

logger = logging.getLogger(__name__)

ALERT_EMAIL = "nicholas.and.dixie@gmail.com"
INITIAL_WAIT = 5  # seconds


def _extract_retry_delay(exc: Exception) -> float | None:
    """Parse the suggested retry delay (seconds) from a Gemini 429 response, if present."""
    text = str(exc)
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", text)
    if match:
        return float(match.group(1))
    return None


def send_alert_email(subject: str, body: str):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = ALERT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.send_message(msg)
    logger.info("Alert email sent.")


def with_retry(func):
    """Retry decorator: 5 attempts with exponential backoff.
    On 5th failure, sends alert email and re-raises."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        wait = INITIAL_WAIT
        for attempt in range(1, 6):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(
                    f"Attempt {attempt}/5 failed for {func.__name__}: {e}\n{tb}"
                )
                if attempt == 5:
                    subject = f"[Notebook OCR] Fatal error in {func.__name__}"
                    body = (
                        f"All 5 retry attempts failed.\n\n"
                        f"Function: {func.__name__}\n"
                        f"Error: {e}\n\n"
                        f"Traceback:\n{tb}"
                    )
                    try:
                        send_alert_email(subject, body)
                    except Exception as email_err:
                        logger.error(f"Failed to send alert email: {email_err}")
                    raise
                # Respect the API's suggested retry delay if present (e.g. Gemini 429s)
                suggested = _extract_retry_delay(e)
                sleep_for = max(wait, suggested) if suggested else wait
                logger.info(f"Retrying in {sleep_for:.0f}s...")
                time.sleep(sleep_for)
                wait *= 2

    return wrapper
