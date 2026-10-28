"""Kiểm tra retry polling không làm phát lại thao tác ghi hoặc bỏ qua quyền."""

import runpy
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from urllib.error import HTTPError, URLError

import pytest


@pytest.fixture
def adapter(monkeypatch):
    sdk = ModuleType("airflow.sdk")
    sdk.get_current_context = lambda: {}
    sdk.task = lambda **kw: lambda function: function
    exceptions = ModuleType("airflow.sdk.exceptions")
    exceptions.AirflowFailException = RuntimeError
    monkeypatch.setitem(sys.modules, "airflow", ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "airflow.sdk.exceptions", exceptions)
    monkeypatch.setenv("CAPTURE_RUNNER_TOKEN", "test-worker")
    namespace = runpy.run_path(str(Path(__file__).parents[2] / "src/fm_mcp/collector/airflow_tasks.py"))
    monkeypatch.setattr(namespace["time"], "sleep", lambda _: None)
    return namespace["runner_request"]


@pytest.mark.parametrize("error", [HTTPError("http://runner", 500, "temporary", {}, None), URLError("offline")])
def test_poll_recovers_from_transient_failure(adapter, monkeypatch, error):
    calls = []

    @contextmanager
    def request(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise error
        yield type("Response", (), {"read": lambda self, size: b'{"status":"running"}'})()

    monkeypatch.setitem(adapter.__globals__, "build_opener", lambda *args: type("Opener", (), {"open": staticmethod(request)})())
    assert adapter("GET", "/runs/abc/steps/transform") == {"status": "running"}
    assert len(calls) == 2


@pytest.mark.parametrize("method,code,count", [("POST", 500, 1), ("GET", 401, 1), ("GET", 409, 1), ("GET", 503, 6)])
def test_poll_never_replays_writes_or_permanent_errors(adapter, monkeypatch, method, code, count):
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        raise HTTPError("http://runner", code, "failure", {}, None)

    monkeypatch.setitem(adapter.__globals__, "build_opener", lambda *args: type("Opener", (), {"open": staticmethod(request)})())
    with pytest.raises(HTTPError):
        adapter(method, "/runs/abc/steps/transform")
    assert len(calls) == count
