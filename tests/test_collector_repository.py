"""Kiểm thử contract và tenant isolation của pipeline; PostgreSQL integration bật riêng."""

import os
from uuid import uuid4

import pytest
from fm_mcp.collector.repository import STEPS, PipelineConflict, PipelineStore


def test_airflow_submit_uses_stable_run_id_and_sends_no_source_config(monkeypatch):
    import httpx
    from fm_mcp.collector.airflow_client import AirflowClient

    requests = []
    real_client = httpx.Client

    def handler(request):
        import json
        requests.append(request)
        assert json.loads(request.content) == {"dag_run_id": "capture__abc", "logical_date": None,
                                               "conf": {"run_id": "abc", "org_id": "demo"}}
        return httpx.Response(200, json={"dag_run_id": "capture__abc"})

    monkeypatch.setenv("TITAN_AIRFLOW_TOKEN", "service-test")
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    AirflowClient().submit({"id": "abc", "org_id": "demo", "context": {"password": "not-in-conf"}})
    assert len(requests) == 1
@pytest.mark.parametrize("healthy,paused,import_errors,expected", [
    (True, False, False, True),
    (False, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
])
def test_readiness_requires_healthy_scheduler_and_runnable_dag(monkeypatch, healthy, paused, import_errors, expected):
    import httpx
    from fm_mcp.collector.airflow_client import AirflowClient

    real_client = httpx.Client

    def handler(request):
        if request.url.path == "/api/v2/monitor/health":
            return httpx.Response(200, json={name: {"status": "healthy" if healthy else "unhealthy"}
                                            for name in ("metadatabase", "scheduler", "dag_processor")})
        assert request.url.path == "/api/v2/dags/fm_data_capture"
        assert request.headers["Authorization"] == "Bearer service-test"
        return httpx.Response(200, json={"is_paused": paused, "has_import_errors": import_errors})

    monkeypatch.setenv("TITAN_AIRFLOW_TOKEN", "service-test")
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert AirflowClient().ready() is expected


def test_dispatch_conflict_verifies_existing_run_instead_of_creating_another(monkeypatch):
    import httpx
    from fm_mcp.collector.airflow_client import AirflowClient

    calls = []
    real_client = httpx.Client

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(409)
        assert request.url.path == "/api/v2/dags/fm_data_capture/dagRuns/capture__abc"
        return httpx.Response(200, json={"dag_run_id": "capture__abc"})

    monkeypatch.setenv("TITAN_AIRFLOW_TOKEN", "service-test")
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    AirflowClient().submit({"id": "abc", "org_id": "demo"})
    assert calls == ["POST", "GET"]


@pytest.fixture
def repository():
    if os.getenv("TITAN_PIPELINE_INTEGRATION") != "1":
        pytest.skip("set TITAN_PIPELINE_INTEGRATION=1 for dedicated pipeline metadata checks")
    store = PipelineStore()
    store.migrate()
    org = "test_pipe_" + uuid4().hex[:12]
    yield store, org
    # Chỉ xóa metadata test của org ngẫu nhiên vừa tạo, không đụng run ứng dụng.
    with store.connect() as db:
        db.execute("DELETE FROM capture.pipeline_events WHERE run_id IN (SELECT id FROM capture.pipeline_runs WHERE org_id=%s)", (org,))
        db.execute("DELETE FROM capture.pipeline_steps WHERE run_id IN (SELECT id FROM capture.pipeline_runs WHERE org_id=%s)", (org,))
        db.execute("DELETE FROM capture.pipeline_runs WHERE org_id=%s", (org,))


def create(store, org):
    return store.create({"id": uuid4().hex, "org_id": org, "connection_id": "bms_fake"}, "bms",
                        {"tenant": {"secret_ref": "private"}})


def test_pipeline_public_response_is_tenant_scoped_and_redacted(repository):
    store, org = repository
    run = create(store, org)
    public = store.get(org, run["id"])
    assert "context" not in public and all("token" not in s and "output" not in s for s in public["steps"])
    with pytest.raises(LookupError):
        store.get("another_tenant", run["id"])
    assert store.list("another_tenant")["total"] == 0


def test_pipeline_begin_deduplicates_and_keeps_step_order(repository):
    store, org = repository
    run = create(store, org)
    with pytest.raises(PipelineConflict):
        store.begin(org, run["id"], "capture", 1)
    first = store.begin(org, run["id"], "prepare", 1)
    second = store.begin(org, run["id"], "prepare", 1)
    assert first["token"] == second["token"] and not second.get("execute")
    store.pulse(run["id"], "prepare", first["token"], {"rows": 12, "password": "do-not-store"})
    store.finish_step(run["id"], first, output={"private": "not-public"})
    public = store.get(org, run["id"])
    step = [s for s in public["steps"] if s["name"] == "prepare"][-1]
    assert step["progress"] == {"rows": 12}
    assert store.begin(org, run["id"], "prepare", 2)["status"] == "succeeded"


def test_retry_keeps_prior_attempt_and_capture_is_not_retried(repository):
    store, org = repository
    run = create(store, org)
    for name in ("prepare", "validate_source"):
        step = store.begin(org, run["id"], name, 1)
        store.finish_step(run["id"], step)
    step = store.begin(org, run["id"], "capture", 1)
    store.finish_step(run["id"], step, error_code="SourceDisconnected")
    with pytest.raises(PipelineConflict, match="automatically retried"):
        store.begin(org, run["id"], "capture", 2)
    assert store.complete(org, run["id"]) == "failed"
    assert store.get(org, run["id"])["status"] == "failed"


def test_pipeline_cancel_and_success_are_not_confused(repository):
    store, org = repository
    run = create(store, org)
    for name in STEPS[:-1]:
        step = store.begin(org, run["id"], name, 1)
        store.finish_step(run["id"], step)
    assert store.complete(org, run["id"]) == "succeeded"
    another = create(store, org)
    store.cancel(org, another["id"])
    assert store.complete(org, another["id"]) == "cancelled"


def test_load_retry_reuses_bronze_without_reopening_capture(repository):
    store, org = repository
    first = create(store, org)
    for name in STEPS[:4]:
        step = store.begin(org, first["id"], name, 1)
        store.finish_step(first["id"], step)
    step = store.begin(org, first["id"], "load_raw", 1)
    store.finish_step(first["id"], step, error_code="WarehouseUnavailable")
    assert store.complete(org, first["id"]) == "failed"
    assert store.get(org, first["id"])["can_retry"]
    second = store.create({"id": first["capture_id"], "org_id": org, "connection_id": first["connection_id"]},
                          "bms", first["context"], retry_of=first["id"])
    assert second["capture_id"] == first["capture_id"]
    assert not store.get(org, first["id"])["can_retry"]
    assert store.begin(org, second["id"], "capture", 1)["status"] == "skipped"
    prepare = store.begin(org, second["id"], "prepare", 1)
    store.finish_step(second["id"], prepare)
    verify = store.begin(org, second["id"], "verify_bronze", 1)
    store.finish_step(second["id"], verify)
    load = store.begin(org, second["id"], "load_raw", 1)
    store.finish_step(second["id"], load)
    assert store.get(org, second["id"])["retry_of"] == first["id"]


def test_reconciliation_only_finalizes_stopped_dags_without_live_workers(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import httpx
    from fm_mcp.collector.dispatcher import CollectorDispatcher

    now = datetime.now(UTC)
    runs = [
        {"id": "stopped", "org_id": "demo", "steps": []},
        {"id": "live", "org_id": "demo", "steps": [{"name": "capture", "status": "running", "heartbeat_at": now}]},
        {"id": "scheduled", "org_id": "demo", "steps": []},
    ]
    calls = []
    real_client = httpx.Client

    def handler(request):
        calls.append(request)
        return httpx.Response(202, json={"status": "running"})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    repository = SimpleNamespace(active=lambda: runs)
    client = SimpleNamespace(state=lambda run: "running" if run["id"] == "scheduled" else "failed")
    CollectorDispatcher(SimpleNamespace(repository=repository, scheduler=client)).reconcile()
    assert len(calls) == 1 and calls[0].url.path == "/runs/stopped/steps/finalize"
