"""
Lightweight SMTP mailer for the API.

Why this exists:
- Your password reset flow creates a token but had no delivery layer.
- This module is additive only; it does not change existing endpoints.
- Wire it by calling `send_password_reset_email(...)` from your reset handler.

Config (from environment):
  EMAIL_ENABLED=0|1
  SMTP_HOST, SMTP_PORT=587
  SMTP_STARTTLS=1|0
  SMTP_SSL=0|1
  SMTP_USER, SMTP_PASSWORD
  SMTP_FROM (e.g., "Detecktiv <no-reply@your-domain>")
Optional:
  SERVICE_NAME (used in subject), FRONTEND_URL (used in body if you pass just a path)
"""

from __future__ import annotations

import os
import ssl
import smtplib
import logging
from typing import Iterable, Mapping, Optional, Tuple
from email.message import EmailMessage
from urllib.parse import urljoin

logger = logging.getLogger("app.services.mailer")


def _getenv_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _coalesce_env(*keys: str, default: Optional[str] = None) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return default


def is_email_enabled() -> bool:
    return _getenv_bool("EMAIL_ENABLED", False)


def _build_message(
    subject: str,
    sender: str,
    to: Iterable[str],
    text_body: str,
    html_body: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    reply_to: Optional[str] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(list(to))
    if cc:
        msg["Cc"] = ", ".join(list(cc))
    if reply_to:
        msg["Reply-To"] = reply_to
    if headers:
        for k, v in headers.items():
            # Avoid clobbering standard headers
            if k.lower() in {"subject", "from", "to", "cc", "bcc", "reply-to"}:
                continue
            msg[k] = v

    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    # BCC isn't a header by design; keep track via return
    return msg


def _smtp_connect() -> Tuple[smtplib.SMTP, Optional[str]]:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = _getenv_bool("SMTP_SSL", False)
    use_starttls = _getenv_bool("SMTP_STARTTLS", True)

    if not host:
        return None, "SMTP_HOST not set"

    timeout = 20
    try:
        if use_ssl:
            context = ssl.create_default_context()
            client = smtplib.SMTP_SSL(
                host=host, port=port, timeout=timeout, context=context
            )
        else:
            client = smtplib.SMTP(host=host, port=port, timeout=timeout)
            client.ehlo()
            if use_starttls:
                context = ssl.create_default_context()
                client.starttls(context=context)
        return client, None
    except Exception as e:
        return None, f"SMTP connect error: {e}"


def send_email(
    to: Iterable[str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    *,
    sender: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    reply_to: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send an email via SMTP/STARTTLS/SSL using env configuration.
    Returns (success, error_message_if_any).
    """
    if not is_email_enabled():
        logger.warning("EMAIL_ENABLED=0; skipping actual send (dry).")
        return False, "EMAIL_DISABLED"

    sender = sender or os.getenv("SMTP_FROM", "Detecktiv <no-reply@localhost>")
    to_list = list(to or [])
    cc_list = list(cc or [])
    bcc_list = list(bcc or [])
    if not to_list:
        return False, "no recipients"

    msg = _build_message(
        subject=subject,
        sender=sender,
        to=to_list,
        text_body=text_body,
        html_body=html_body,
        headers=headers,
        cc=cc_list or None,
        bcc=bcc_list or None,
        reply_to=reply_to,
    )

    client, err = _smtp_connect()
    if err:
        logger.error("SMTP connection failed: %s", err)
        return False, err

    try:
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASSWORD", "")

        if user:
            client.login(user, password)

        # All recipients: To + Cc + Bcc
        rcpt = to_list + cc_list + bcc_list

        client.send_message(msg, from_addr=sender, to_addrs=rcpt)
        logger.info("Email sent: subject=%r to=%r", subject, rcpt)
        return True, None
    except smtplib.SMTPResponseException as e:
        code = getattr(e, "smtp_code", None)
        err_str = f"SMTPResponseException[{code}]: {e}"
        logger.error(err_str)
        return False, err_str
    except Exception as e:
        logger.exception("SMTP send failed")
        return False, f"SMTP send error: {e}"
    finally:
        try:
            client.quit()
        except Exception:
            try:
                client.close()
            except Exception:
                pass


def build_password_reset_bodies(
    reset_url: str,
    *,
    expires_minutes: int = 60,
    app_name: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Build plaintext and HTML bodies for password reset.
    If `reset_url` is a path, FRONTEND_URL is used as base.
    """
    app_name = app_name or _coalesce_env("SERVICE_NAME", default="Detecktiv")

    # If the provided URL is relative, join with FRONTEND_URL
    if reset_url and reset_url.startswith("/"):
        base = os.getenv("FRONTEND_URL", "").strip()
        if base:
            reset_url = urljoin(
                base if base.endswith("/") else base + "/", reset_url.lstrip("/")
            )

    text = (
        f"You requested a password reset for your {app_name} account.\n\n"
        f"Reset link: {reset_url}\n\n"
        f"This link will expire in {expires_minutes} minutes. "
        "If you did not request this, you can safely ignore this email.\n\n"
        f"— {app_name} Team"
    )

    html = f"""\
<!doctype html>
<html>
  <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height:1.5; color:#111;">
    <div style="max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="margin:0 0 12px 0;">Reset your {app_name} password</h2>
      <p>You requested a password reset for your {app_name} account.</p>
      <p>
        <a href="{reset_url}" style="display:inline-block;padding:10px 16px;border-radius:6px;text-decoration:none;border:1px solid #444;">
          Open secure reset link
        </a>
      </p>
      <p style="color:#444;">This link will expire in {expires_minutes} minutes.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#666;font-size:13px;">If you did not request this, you can safely ignore this email.</p>
      <p style="color:#666;font-size:13px;">— {app_name} Team</p>
    </div>
  </body>
</html>
"""
    return text, html


def send_password_reset_email(
    recipient_email: str,
    reset_url: str,
    *,
    expires_minutes: int = 60,
    app_name: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Convenience wrapper to deliver a password reset email.

    Example wiring inside your endpoint after creating a token + URL:
        ok, err = send_password_reset_email(user.email, reset_url, expires_minutes=60)
        if not ok:
            # log but do not leak internal details to client
            logger.warning("Password reset email not sent: %s", err)
    """
    app_name = app_name or _coalesce_env("SERVICE_NAME", default="Detecktiv")
    subject = f"{app_name} — Password reset instructions"

    text, html = build_password_reset_bodies(
        reset_url=reset_url,
        expires_minutes=expires_minutes,
        app_name=app_name,
    )
    sender = os.getenv("SMTP_FROM", f"{app_name} <no-reply@localhost>")

    return send_email(
        to=[recipient_email],
        subject=subject,
        text_body=text,
        html_body=html,
        sender=sender,
        reply_to=reply_to,
    )
