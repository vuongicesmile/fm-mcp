"""MCP chỉ gọi service mới; không trả raw lỗi có thể chứa credential."""

from dataclasses import replace

import httpx
import pytest
from fm_mcp.clients import collector_api


def test_collector_client_calls_service_not_control_plane(monkeypatch):
    real_client = httpx.Client
    def handler(request):
        assert request.url.host == "collector-service.test"
        assert request.url.path == "/internal/tenants/demo/connections/bms/sync"
        assert request.headers["Authorization"] == "Bearer service-test"
        return httpx.Response(202, json={"id": "job", "pipeline_id": "run"})
    monkeypatch.setattr(collector_api, "settings", replace(collector_api.settings, collector_org_id="demo",
        collector_service_url="http://collector-service.test", collector_service_token="service-test"))
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert collector_api.call("POST", "/connections/bms/sync", {"request_key": "request-key"})["pipeline_id"] == "run"


def test_collector_error_keeps_status_but_redacts_response(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(collector_api, "settings", replace(collector_api.settings, collector_org_id="demo", collector_service_token="service-test"))
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(
        lambda _: httpx.Response(409, json={"detail": "sensitive-internal-error"})), **kw))
    with pytest.raises(RuntimeError) as error:
        collector_api.call("POST", "/pipelines/run/retry")
    assert "[409]" in str(error.value) and "sensitive-internal-error" not in str(error.value)
