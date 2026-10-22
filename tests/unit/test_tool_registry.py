from __future__ import annotations

import json
import importlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from fastmcp import Client, FastMCP

from fm_mcp.tools import _client, registry

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
APPROVAL_ID = "22222222-2222-4222-8222-222222222222"
RISK_ID = "33333333-3333-4333-8333-333333333333"


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function
        return register


@pytest.fixture
def tools():
    server = ToolRegistry()
    registry.register_tools(server)
    return server.tools


def test_every_registered_tool_maps_to_its_rest_endpoint(tools, monkeypatch):
    calls = []
    expected = {
        "list_workflows": ("GET", "/api/v1/workflows"),
        "create_workflow": ("POST", "/api/v1/workflows"),
        "create_request": ("POST", "/api/v1/requests"),
        "list_requests": ("GET", "/api/v1/requests"),
        "get_request": ("GET", f"/api/v1/requests/{REQUEST_ID}"),
        "update_request": ("PATCH", f"/api/v1/requests/{REQUEST_ID}"),
        "submit_request": ("POST", f"/api/v1/requests/{REQUEST_ID}/submit"),
        "close_request": ("POST", f"/api/v1/requests/{REQUEST_ID}/close"),
        "get_request_history": ("GET", f"/api/v1/requests/{REQUEST_ID}/history"),
        "get_pending_approvals": ("GET", "/api/v1/approvals/pending"),
        "approve_request": ("POST", f"/api/v1/approvals/{APPROVAL_ID}/approve"),
        "reject_request": ("POST", f"/api/v1/approvals/{APPROVAL_ID}/reject"),
        "get_approval_history": ("GET", f"/api/v1/approvals/{APPROVAL_ID}/history"),
        "create_risk": ("POST", "/api/v1/risks"),
        "update_risk": ("PATCH", f"/api/v1/risks/{RISK_ID}"),
        "get_risk_register": ("GET", "/api/v1/risks?status=open"),
        "assess_risk": ("POST", f"/api/v1/risks/{RISK_ID}/assessments"),
        "get_risk_heatmap": ("GET", "/api/v1/risks/heatmap"),
        "get_notifications": ("GET", "/api/v1/notifications"),
        "send_notification": ("POST", "/api/v1/notifications"),
        "get_overdue_requests": ("GET", "/api/v1/requests/overdue"),
        "test_data_source": ("POST", "/connections/bms_main/test"),
        "get_data_sync_status": ("GET", "/connections/bms_main/capture/status"),
        "list_data_sync_jobs": ("GET", "/connections/bms_main/capture/jobs?limit=20"),
        "sync_data": ("POST", "/connections/bms_main/sync"),
        "cancel_data_sync": ("POST", "/connections/bms_main/capture/cancel"),
        "retry_data_sync": ("POST", "/connections/bms_main/sync/retry"),
    }
    arguments = {
        "create_workflow": ("maintenance", "Maintenance", None, [{"step_order": 1}]),
        "create_request": (REQUEST_ID, "maintenance", "Repair", "Leaking tap", "high"),
        "get_request": (REQUEST_ID,),
        "update_request": (REQUEST_ID, {"title": "Updated"}),
        "submit_request": (REQUEST_ID,),
        "close_request": (REQUEST_ID,),
        "get_request_history": (REQUEST_ID,),
        "approve_request": (APPROVAL_ID, "Approved", "approve-key"),
        "reject_request": (APPROVAL_ID, "Rejected", "reject-key"),
        "get_approval_history": (APPROVAL_ID,),
        "create_risk": ("Leak", "Water leak", "fm-owner", REQUEST_ID, "safety"),
        "update_risk": (RISK_ID, {"status": "mitigated"}),
        "get_risk_register": ("open",),
        "assess_risk": (RISK_ID, 3, 4, "initial", "Observed"),
        "send_notification": ("fm-owner", "fm@example.test", "request.created", "Request created", "Created", REQUEST_ID),
        "test_data_source": ("bms_main",),
        "get_data_sync_status": ("bms_main",),
        "list_data_sync_jobs": ("bms_main",),
        "sync_data": ("bms_main", "sync-key-123"),
        "cancel_data_sync": ("bms_main",),
        "retry_data_sync": ("bms_main",),
    }

    def fake_call(method, path, payload=None, extra_headers=None):
        calls.append((method, path, payload, extra_headers))
        return [] if method == "GET" and path.endswith(("workflows", "history", "heatmap", "assets")) else {}

    monkeypatch.setattr(_client, "_call", fake_call)
    for function in registry.ALL_TOOLS:
        if function.__module__.startswith("fm_mcp.tools.collector"):
            monkeypatch.setattr(importlib.import_module(function.__module__), "call", fake_call)
    profiling_tools = {
        "list_data_profiling_assets", "run_data_profiling", "get_data_profiling_run",
        "get_data_profiling_overview", "get_masked_raw_sample", "seed_data_profiling_demo",
    }
    assert set(tools) == set(expected) | profiling_tools
    for name, function in tools.items():
        if name in profiling_tools:
            continue
        function(*arguments[name]) if name in arguments else function()

    assert len(calls) == len(expected)
    assert {name: (method, path) for name, (method, path, _, _) in zip(tools, calls)} == expected
    assert calls[10][3] == {"Idempotency-Key": "approve-key"}
    assert calls[11][3] == {"Idempotency-Key": "reject-key"}
    assert calls[2][2] == {
        "workflow_definition_id": REQUEST_ID,
        "request_type": "maintenance",
        "title": "Repair",
        "description": "Leaking tap",
        "priority": "high",
        "context": {},
    }
    assert calls[19][2]["channel"] == "email"
    assert calls[19][2]["request_id"] == REQUEST_ID


@pytest.mark.asyncio
async def test_request_lifecycle_through_mcp_protocol(monkeypatch):
    workflow_id = str(UUID(REQUEST_ID))
    request = {
        "id": workflow_id,
        "request_code": "FM-2026-0001",
        "workflow_definition_id": workflow_id,
        "request_type": "maintenance",
        "title": "Fix leaking tap",
        "description": "Building A, level 2",
        "status": "draft",
        "priority": "high",
    }
    history = []
    calls = []

    def fake_api(request_):
        method, path = request_.method, request_.url.path
        payload = request_.read()
        calls.append((method, path, request_.headers.get("X-Authenticated-User-Id")))
        if method == "GET" and path == "/api/v1/workflows":
            return httpx.Response(200, json=[{"id": workflow_id, "code": "MAINT", "name": "Maintenance"}])
        if method == "POST" and path == "/api/v1/requests":
            request.update(json.loads(payload))
            history.append({"from_status": None, "to_status": "draft"})
            return httpx.Response(201, json=dict(request))
        if method == "GET" and path == "/api/v1/requests":
            return httpx.Response(200, json={"items": [dict(request)], "total": 1, "offset": 0, "limit": 50})
        if method == "PATCH" and path == f"/api/v1/requests/{workflow_id}":
            request.update(json.loads(payload))
            return httpx.Response(200, json=dict(request))
        if method == "POST" and path == f"/api/v1/requests/{workflow_id}/submit":
            request["status"] = "in_review"
            request["submitted_at"] = datetime.now(UTC).isoformat()
            history.append({"from_status": "draft", "to_status": "in_review"})
            return httpx.Response(200, json=dict(request))
        if method == "GET" and path == f"/api/v1/requests/{workflow_id}":
            return httpx.Response(200, json=dict(request))
        if method == "GET" and path == f"/api/v1/requests/{workflow_id}/history":
            return httpx.Response(200, json=list(history))
        return httpx.Response(404, json={"detail": f"Unexpected FM API call: {method} {path}"})

    monkeypatch.setattr(_client, "create_client", lambda: httpx.Client(
        base_url="http://fm-api.test",
        transport=httpx.MockTransport(fake_api),
    ))
    monkeypatch.setattr(_client, "settings", replace(_client.settings, mcp_dev_user_id="test-fm-user"))
    server = FastMCP("fm-mcp-test")
    registry.register_tools(server)

    def value(result):
        if result.is_error:
            raise AssertionError(result.content)
        if result.structured_content is not None:
            data = result.structured_content
        else:
            data = json.loads(result.content[0].text)
        if isinstance(data, dict) and set(data) == {"result"}:
            return data["result"]
        return data

    async with Client(server) as client:
        workflows = value(await client.call_tool("list_workflows", {}))
        assert workflows == [{"id": workflow_id, "code": "MAINT", "name": "Maintenance"}]
        created = value(await client.call_tool("create_request", {
            "workflow_definition_id": workflow_id,
            "request_type": "maintenance",
            "title": "Fix leaking tap",
            "description": "Building A, level 2",
            "priority": "high",
        }))
        assert created["status"] == "draft"
        assert value(await client.call_tool("list_requests", {}))["items"][0]["request_code"] == "FM-2026-0001"
        updated = value(await client.call_tool("update_request", {
            "request_id": workflow_id,
            "changes": {"description": "Building A, level 3"},
        }))
        assert updated["description"] == "Building A, level 3"
        assert value(await client.call_tool("get_request", {"request_id": workflow_id}))["title"] == "Fix leaking tap"
        submitted = value(await client.call_tool("submit_request", {"request_id": workflow_id}))
        assert submitted["status"] == "in_review"
        events = value(await client.call_tool("get_request_history", {"request_id": workflow_id}))

    assert [entry["to_status"] for entry in events] == ["draft", "in_review"]
    assert [path for _, path, _ in calls] == [
        "/api/v1/workflows",
        "/api/v1/requests",
        "/api/v1/requests",
        f"/api/v1/requests/{workflow_id}",
        f"/api/v1/requests/{workflow_id}",
        f"/api/v1/requests/{workflow_id}/submit",
        f"/api/v1/requests/{workflow_id}/history",
    ]
    assert all(user_id == "test-fm-user" for _, _, user_id in calls)
