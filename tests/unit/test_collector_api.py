"""Phân quyền riêng operator/worker và contract public của collector service."""

from types import SimpleNamespace

import httpx
import pytest
from fm_mcp.collector.api import app, get_service


@pytest.mark.asyncio
async def test_collector_tokens_are_role_and_tenant_bound(monkeypatch):
    monkeypatch.setenv("FM_COLLECTOR_ORG_ID", "demo")
    monkeypatch.setenv("FM_COLLECTOR_SERVICE_TOKEN", "operator-test")
    monkeypatch.setenv("CAPTURE_RUNNER_TOKEN", "worker-test")
    app.dependency_overrides[get_service] = lambda: SimpleNamespace(
        scheduler=SimpleNamespace(ready=lambda: True),
        repository=SimpleNamespace(get=lambda org, identity, **kw: {"id": identity, "context": {"secret": "private"}}))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://collector") as c:
            assert (await c.get("/internal/tenants/demo/health")).status_code == 401
            operator = {"Authorization": "Bearer operator-test"}
            worker = {"Authorization": "Bearer worker-test"}
            assert (await c.get("/internal/tenants/demo/health", headers=operator)).status_code == 200
            assert (await c.get("/internal/tenants/other/health", headers=operator)).status_code == 403
            assert (await c.get("/internal/worker/demo/runs/abc", headers=operator)).status_code == 401
            assert (await c.get("/internal/worker/other/runs/abc", headers=worker)).status_code == 403
            assert (await c.get("/internal/worker/demo/runs/abc", headers=worker)).status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_collector_sync_rejects_unknown_payload_fields(monkeypatch):
    monkeypatch.setenv("FM_COLLECTOR_ORG_ID", "demo")
    monkeypatch.setenv("FM_COLLECTOR_SERVICE_TOKEN", "operator-test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://collector") as c:
        response = await c.post("/internal/tenants/demo/connections/bms/sync", headers={"Authorization": "Bearer operator-test"},
                                json={"request_key": "request-key", "config": {"password": "never-from-tool"}})
        assert response.status_code == 422


def test_service_sync_creates_job_and_outbox_in_one_transaction(monkeypatch):
    from contextlib import nullcontext

    import fm_mcp.collector.service as module

    transaction = object()
    job = {"id": "a" * 32}

    class Source:
        connector = "bms"
        def __init__(self, name):
            assert name == "bms"
        def connect(self):
            return nullcontext(transaction)
        def enqueue(self, org, connection, key, config, db):
            assert db is transaction and config == {"source": "validated"}
            return job

    class Repository:
        def create(self, received, connector, context, **kw):
            assert received is job and kw["transaction"] is transaction
            return {"id": "pipeline", "org_id": "demo"}
        def dispatched(self, identity, *args):
            assert identity == "pipeline"

    dispatched = []
    monkeypatch.setattr(module, "SourceJobs", Source)
    service = module.CollectorService(Repository(), SimpleNamespace(submit=dispatched.append),
        contexts=lambda *args, **kw: {"connector": "bms", "enabled": True, "config": {"source": "validated"}, "context": {}})
    monkeypatch.setattr(service, "public_job", lambda org, received: {"id": received["id"]})
    assert service.sync("demo", "bms", "request-key")["id"] == job["id"]
    assert len(dispatched) == 1
