import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone
from extensions import db
from models import EmailLog


def send_notification(evaluation, email_type, subject, text_body, html_body):
    recipient = evaluation.submission.user.email
    key = f"evaluation:{evaluation.id}:{email_type}"
    existing = EmailLog.query.filter_by(idempotency_key=key).first()
    if existing and existing.delivery_status == "sent":
        return existing
    log = existing or EmailLog(
        evaluation_id=evaluation.id,
        recipient=recipient,
        email_type=email_type,
        idempotency_key=key,
    )
    if existing is None:
        db.session.add(log)
    if not evaluation.submission.user.email_verified:
        log.delivery_status = "blocked"
        log.error_summary = "Recipient email has not been verified."
        db.session.commit()
        return log
    log.attempts = (log.attempts or 0) + 1
    if os.getenv("EMAIL_ENABLED", "false").lower() != "true":
        log.delivery_status = "disabled"
        log.error_summary = "Email delivery is disabled by configuration."
        db.session.commit()
        return log
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("SENDER_EMAIL", "")
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    try:
        host = os.environ["SMTP_HOST"]
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.environ["SMTP_USERNAME"]
        password = os.environ["SMTP_PASSWORD"]
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)
        log.delivery_status = "sent"
        log.sent_at = datetime.now(timezone.utc)
        log.error_summary = None
    except Exception as exc:
        log.delivery_status = "failed"
        log.error_summary = type(exc).__name__
    db.session.commit()
    return log
