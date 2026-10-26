"""Minimal SMTP adapter used by the notification delivery worker."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from html import escape
import re
import smtplib
from typing import Any

from fm_mcp.api.settings import api_settings

_TOKEN = re.compile(r"{{\s*([a-zA-Z_][\w.]*)\s*}}")


def render_notification_html(subject: str, body: str) -> str:
    """Tạo email HTML có fallback text; escape toàn bộ nội dung người dùng."""
    paragraphs = "".join(
        f'<p style="margin:0 0 14px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere">{escape(part)}</p>'
        for part in body.split("\n\n") if part.strip()
    )
    return f'''<!doctype html><html lang="vi"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f3f6fb;font-family:Arial,Helvetica,sans-serif;color:#24344b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:white;border:1px solid #dce5f0;border-radius:16px;overflow:hidden">
<tr><td style="padding:26px 32px;background:#1677ff;color:white"><strong style="font-size:25px">titan data</strong><div style="font-size:12px;margin-top:8px;letter-spacing:2px">FACILITY MANAGEMENT</div></td></tr>
<tr><td style="padding:30px 32px 10px"><span style="font-size:12px;font-weight:bold;color:#1557ae;background:#eaf3ff;padding:7px 12px;border-radius:20px">THÔNG BÁO CÔNG VIỆC</span>
<h1 style="font-size:24px;line-height:1.4;margin:22px 0 14px;overflow-wrap:anywhere">{escape(subject)}</h1>
<div style="font-size:15px">{paragraphs}</div></td></tr>
<tr><td style="padding:8px 32px 30px"><div style="padding:18px;background:#f1f6ff;border-left:3px solid #1677ff;font-size:14px;line-height:1.7"><strong>Bước tiếp theo</strong><br>Mở Titan Portal → Yêu cầu để xem chi tiết, dữ liệu đính kèm và lịch sử xử lý. Thông báo này không thay thế thao tác phê duyệt.</div></td></tr>
<tr><td style="padding:20px 32px;border-top:1px solid #e5eaf2;color:#64748b;font-size:12px;line-height:1.7">Titan Data · Kết nối dữ liệu và công việc<br>Email tự động từ hệ thống FM. Không gửi mật khẩu hoặc thông tin nhạy cảm qua email phản hồi.</td></tr>
</table></td></tr></table></body></html>'''


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
        message.add_alternative(render_notification_html(subject, body), subtype="html")
        with smtplib.SMTP(api_settings.smtp_host, api_settings.smtp_port, timeout=api_settings.smtp_timeout_seconds) as smtp:
            smtp.ehlo()
            if api_settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if api_settings.smtp_username:
                smtp.login(api_settings.smtp_username, api_settings.smtp_password or "")
            smtp.send_message(message)
