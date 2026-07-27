from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from .models import Brief


def send_brief(brief: Brief) -> None:
    required = ["SMTP_HOST", "SMTP_PORT", "EMAIL_FROM", "EMAIL_TO"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing email configuration: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = brief.subject
    message["From"] = os.environ["EMAIL_FROM"]
    message["To"] = os.environ["EMAIL_TO"]
    message.set_content(brief.plain_text)
    message.add_alternative(brief.html, subtype="html")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    context = ssl.create_default_context()
    use_ssl = os.getenv("SMTP_SSL", "false").lower() == "true"
    if use_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
    with smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true" and not use_ssl:
            smtp.starttls(context=context)
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
