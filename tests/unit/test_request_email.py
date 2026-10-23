from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from fm_mcp.domain.models.workflow import FMRequest, Notification
from fm_mcp.domain.services.workflow import WorkflowService
from fm_mcp.schemas.workflow import RequestCreate


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
