"""Minimal SMTP adapter used by the notification delivery worker."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
import re
import smtplib
from typing import Any

from fm_mcp.api.settings import api_settings

_TOKEN = re.compile(r"{{\s*([a-zA-Z_][\w.]*)\s*}}")


def render_template(template: str, payload: dict[str, Any]) -> str:
    """Render only dotted payload fields; templates never evaluate Python code."""
    def replace(match: re.Match[str]) -> str:
        value: Any = payload
        for part in match.group(1).split("."):
            if not isinstance(value, dict) or part not in value:
                return ""
            value = value[part]
        return str(value)

    return _TOKEN.sub(replace, template)


class SMTPEmailSender:
    async def send(self, recipient: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_sync, recipient, subject, body)

    @staticmethod
    def _send_sync(recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = api_settings.smtp_from_address
        message["To"] = recipient
        message["Subject"] = subject.replace("\r", "").replace("\n", " ")
        message.set_content(body)
        with smtplib.SMTP(api_settings.smtp_host, api_settings.smtp_port, timeout=api_settings.smtp_timeout_seconds) as smtp:
            smtp.ehlo()
            if api_settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if api_settings.smtp_username:
                smtp.login(api_settings.smtp_username, api_settings.smtp_password or "")
            smtp.send_message(message)
