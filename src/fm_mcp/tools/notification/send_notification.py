"""Send a notification through FM Backend."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def send_notification(
    recipient_id: str,
    recipient_address: str,
    event_code: str,
    body: str,
    subject: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Queue email; the trusted SMTP dispatcher delivers it asynchronously."""
    payload: dict[str, Any] = {
        "recipient_id": recipient_id,
        "recipient_address": recipient_address,
        "channel": "email",
        "event_code": event_code,
        "payload": {"body": body},
    }
    if request_id:
        payload["request_id"] = str(UUID(request_id))
    if subject:
        payload["payload"]["subject"] = subject
    result = _client._call("POST", "/api/v1/notifications", payload)
    assert isinstance(result, dict)
    return result
