import logging
import os
import smtplib
import time
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

logger = logging.getLogger(__name__)

ALERT_EMAIL = "nicholas.and.dixie@gmail.com"
INITIAL_WAIT = 5  # seconds
MAX_ATTEMPTS = 5


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


def send_failure_alert(context: str, exc: Exception):
    """Email the error and full traceback. Never raises: a broken email setup
    must not hide the original error."""
    tb = "".join(traceback.format_exception(exc))
    subject = f"[Notebook OCR] Pipeline stopped: {context}"
    body = (
        f"The pipeline hit an unrecoverable error and has stopped.\n\n"
        f"Failed while: {context}\n"
        f"Error: {exc}\n\n"
        f"Traceback:\n{tb}"
    )
    try:
        send_alert_email(subject, body)
    except Exception as email_err:
        logger.error(f"Failed to send alert email: {email_err}")


def with_retry(func):
    """Retry decorator: MAX_ATTEMPTS attempts with exponential backoff, then re-raise.
    The alert email is sent by the caller that finally handles the error (main.py)."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        wait = INITIAL_WAIT
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Attempt {attempt}/{MAX_ATTEMPTS} failed for {func.__name__}: {e}",
                    exc_info=True,
                )
                if attempt == MAX_ATTEMPTS:
                    raise
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)
                wait *= 2

    return wrapper
