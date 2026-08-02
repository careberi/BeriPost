"""Email Neil a copy of each post after it publishes, via SMTP.

Needs SMTP_HOST, SMTP_USER, SMTP_PASS, NOTIFY_TO in .env (and SMTP_PORT,
default 587). Fails soft: if email is not configured or sending fails, it logs
a warning and returns False so the run continues.
"""
from __future__ import annotations

import logging
import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)


def notify_post(config: Config, pillar: str, caption: str, image_path: str | None,
                fb_post_id: str | None = None) -> bool:
    if not config.email_ready:
        log.info("Email not configured; skipping notification.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"BeriPost published a {pillar} post"
    msg["From"] = config.smtp_user
    msg["To"] = config.notify_to
    fb_line = f"\n\nFacebook post id: {fb_post_id}" if fb_post_id else ""
    msg.set_content(
        f"BeriPost just published a {pillar} post to your Facebook Page.\n\n"
        f"--- caption ---\n{caption}{fb_line}\n\n"
        "The image is attached. Reply is not monitored; to change future posts, "
        "give feedback with:  python run.py feedback \"your note\""
    )

    if image_path and Path(image_path).exists():
        try:
            data = Path(image_path).read_bytes()
            ctype, _ = mimetypes.guess_type(image_path)
            maintype, subtype = (ctype or "image/png").split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype,
                               filename=Path(image_path).name)
        except Exception:  # noqa: BLE001
            log.exception("Could not attach image to the email.")

    try:
        if config.smtp_port == 465:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port,
                                  context=ssl.create_default_context()) as s:
                s.login(config.smtp_user, config.smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(config.smtp_user, config.smtp_pass)
                s.send_message(msg)
        log.info("Emailed a copy of the post to %s", config.notify_to)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Could not send the notification email.")
        return False
