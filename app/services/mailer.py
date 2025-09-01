# app/services/mailer.py
from __future__ import annotations

import os
import ssl
import smtplib
import logging
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    use_ssl: bool
    starttls: bool
    from_email: str
    timeout: float = 10.0


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _smtp_config_from_env() -> Optional[SMTPConfig]:
    host = os.getenv("SMTP_HOST")
    if not host:
        return None  # no SMTP configured, caller can fall back to console

    port = int(os.getenv("SMTP_PORT", "587") or "587")
    user = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")
    use_ssl = _env_bool("SMTP_SSL", False)
    starttls = _env_bool("SMTP_STARTTLS", not use_ssl)  # default STARTTLS if SSL is false
    from_email = os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or "no-reply@localhost"

    return SMTPConfig(
        host=host,
        port=port,
        username=user,
        password=pwd,
        use_ssl=use_ssl,
        starttls=starttls,
        from_email=from_email,
        timeout=float(os.getenv("SMTP_TIMEOUT", "10.0") or "10.0"),
    )


def _mask_token(tok: str, head: int = 6, tail: int = 4) -> str:
    s = (tok or "").strip()
    if len(s) <= head + tail:
        return "*" * len(s)
    return f"{s[:head]}...{s[-tail:]}"


class Mailer:
    """
    Lightweight mail sender with:
      - SMTP mode (TLS/SSL) when SMTP_* env is present
      - Console mode otherwise (prints email contents for dev)
    """

    def __init__(self, smtp: Optional[SMTPConfig] = None) -> None:
        self.smtp = smtp or _smtp_config_from_env()
        self.mode = "smtp" if self.smtp else "console"
        log.info("Mailer initialized in %s mode", self.mode)

    # ---------------- Low-level send ----------------
    def _send_smtp(self, to_email: str, subject: str, text_body: str, html_body: Optional[str]) -> bool:
        assert self.smtp is not None
        msg = EmailMessage()
        msg["From"] = self.smtp.from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        if html_body:
            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")
        else:
            msg.set_content(text_body)

        context = ssl.create_default_context()
        try:
            if self.smtp.use_ssl:
                with smtplib.SMTP_SSL(self.smtp.host, self.smtp.port, timeout=self.smtp.timeout, context=context) as server:
                    self._smtp_login_if_needed(server)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=self.smtp.timeout) as server:
                    if self.smtp.starttls:
                        server.starttls(context=context)
                    self._smtp_login_if_needed(server)
                    server.send_message(msg)
            return True
        except Exception as e:
            # Do not include message contents in logs
            log.error("SMTP send failed: %s", e)
            return False

    def _smtp_login_if_needed(self, server: smtplib.SMTP) -> None:
        if self.smtp and self.smtp.username:
            try:
                server.login(self.smtp.username, self.smtp.password or "")
            except Exception as e:
                log.error("SMTP login failed: %s", e)
                raise

    def _send_console(self, to_email: str, subject: str, text_body: str, html_body: Optional[str]) -> bool:
        # Dev convenience: print minimal info; avoid dumping secrets
        snippet = (text_body or "").replace("\n", " ")[:200]
        log.warning("Console mail -> To: %s | Subject: %s | Preview: %s ...", to_email, subject, snippet)
        return True

    # ---------------- Public API ----------------
    def send_email(self, to_email: str, subject: str, text_body: str, html_body: Optional[str] = None) -> bool:
        """
        Returns True on success, False on failure. Never raises.
        """
        if self.mode == "smtp":
            return self._send_smtp(to_email, subject, text_body, html_body)
        return self._send_console(to_email, subject, text_body, html_body)

    def send_password_reset(self, to_email: str, token: str, reset_link: Optional[str], expires_at_epoch: Optional[int]) -> bool:
        """
        Sends a password reset email. If a `reset_link` is provided, it will be used;
        otherwise we include the token and simple instructions. Token is masked in logs.
        """
        masked = _mask_token(token)
        subject = "Password reset instructions"

        if reset_link:
            text = (
                "We received a request to reset your password.\n\n"
                f"Click the link below (valid for a limited time):\n{reset_link}\n\n"
                "If you did not request this, you can ignore this email."
            )
            html = f"""
                <p>We received a request to reset your password.</p>
                <p><a href="{reset_link}">Reset your password</a></p>
                <p style="color:#666">If you did not request this, you can ignore this email.</p>
            """
        else:
            text = (
                "We received a request to reset your password.\n\n"
                "Use the following token in the application (valid for a limited time):\n"
                f"{token}\n\n"
                "If you did not request this, you can ignore this email."
            )
            html = None  # avoid putting token in HTML emails unless you really want to

        ok = self.send_email(to_email, subject, text, html)
        if ok:
            log.info("Password reset email sent to %s (token=%s)", to_email, masked)
        else:
            log.error("Password reset email FAILED for %s (token=%s)", to_email, masked)
        return ok


# Simple module-level singleton (optional)
_mailer_singleton: Optional[Mailer] = None

def get_mailer() -> Mailer:
    global _mailer_singleton
    if _mailer_singleton is None:
        _mailer_singleton = Mailer()
    return _mailer_singleton
