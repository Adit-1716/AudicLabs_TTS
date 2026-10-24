import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.models import Notification, NotificationHistory, User


def notify(
    db,
    user_id: str,
    title: str,
    body: str,
    organization_id: str | None = None,
    link: str | None = None,
    channels: list[str] | None = None,
):
    channels = channels or ["in_app"]
    n = Notification(
        user_id=user_id,
        organization_id=organization_id,
        title=title,
        body=body,
        link=link,
        channel=",".join(channels),
    )
    db.add(n)
    db.flush()
    for ch in channels:
        db.add(NotificationHistory(notification_id=n.id, channel=ch, status="queued" if ch != "in_app" else "sent"))
    user = db.get(User, user_id)
    if user and "email" in channels:
        asyncio.get_event_loop().create_task(_email(user.email, title, body)) if False else None
        # Email is sent by the worker/API thread synchronously if SMTP is configured.
        _send_email_sync(user.email, title, body)
    if user and "sms" in channels and user.phone:
        _sms_sync(user.phone, f"{title}: {body}")
    return n


def _send_email_sync(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        return
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def _sms_sync(phone: str, body: str) -> None:
    if not settings.twilio_account_sid:
        return
    import httpx

    httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        data={"From": settings.twilio_from, "To": phone, "Body": body},
        timeout=10,
    )


def mark_read(db, notification: Notification) -> None:
    notification.read_at = datetime.now(timezone.utc)
