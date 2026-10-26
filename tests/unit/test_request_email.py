from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from fm_mcp.domain.models.workflow import FMRequest, Notification
from fm_mcp.domain.services.workflow import WorkflowService
from fm_mcp.schemas.workflow import RequestCreate
from fm_mcp.infrastructure.email import SMTPEmailSender, render_notification_html


def test_html_email_escapes_untrusted_content():
    html = render_notification_html('<img src=x onerror="alert(1)">', 'Title: <script>bad()</script>\n\nDetails & notes')
    assert '<script>' not in html
    assert '<img src=x' not in html
    assert '&lt;script&gt;' in html
    assert 'Details &amp; notes' in html
    assert 'Bước tiếp theo' in html


def test_smtp_preserves_plain_text_and_adds_html(monkeypatch):
    messages = []

    class SMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def ehlo(self):
            pass

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr('fm_mcp.infrastructure.email.smtplib.SMTP', SMTP)
    monkeypatch.setattr('fm_mcp.infrastructure.email.api_settings.smtp_username', None)
    monkeypatch.setattr('fm_mcp.infrastructure.email.api_settings.smtp_starttls', False)
    SMTPEmailSender._send_sync('demo@example.test', 'Request created', 'Safe <text>')
    assert messages[0].get_body(preferencelist=('plain',)).get_content().strip() == 'Safe <text>'
    assert 'Safe &lt;text&gt;' in messages[0].get_body(preferencelist=('html',)).get_content()


class FakeSession:
    def __init__(self):
        self.items = []

    async def scalar(self, _statement):
        return SimpleNamespace(id=uuid4())

    def add(self, item):
        self.items.append(item)

    async def flush(self):
        for item in self.items:
            if isinstance(item, FMRequest) and item.id is None:
                item.id = uuid4()

    async def refresh(self, _item):
        return None


@pytest.mark.asyncio
async def test_creating_request_queues_confirmation_email(monkeypatch):
    monkeypatch.setattr(
        "fm_mcp.domain.services.workflow.api_settings.request_notification_email",
        "fm-requests@example.test",
    )
    session = FakeSession()
    request = await WorkflowService(session, "local-developer").create_request(
        RequestCreate(
            workflow_definition_id=uuid4(),
            request_type="maintenance",
            title="Repair air conditioner",
            priority="high",
        )
    )

    notification = next(item for item in session.items if isinstance(item, Notification))
    assert notification.request_id == request.id
    assert notification.recipient_id == "local-developer"
    assert notification.recipient_address == "fm-requests@example.test"
    assert notification.channel == "email"
    assert notification.event_code == "request_created"
    assert notification.payload["request_code"] == request.request_code


@pytest.mark.asyncio
async def test_creating_request_requires_configured_email_recipient(monkeypatch):
    monkeypatch.setattr(
        "fm_mcp.domain.services.workflow.api_settings.request_notification_email",
        None,
    )

    with pytest.raises(HTTPException) as error:
        await WorkflowService(FakeSession(), "local-developer").create_request(
            RequestCreate(
                workflow_definition_id=uuid4(),
                request_type="maintenance",
                title="Repair air conditioner",
            )
        )

    assert error.value.status_code == 503
