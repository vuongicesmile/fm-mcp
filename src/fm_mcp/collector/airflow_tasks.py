"""Task adapter do Collector Service sở hữu; không chuyển payload qua XCom."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from airflow.sdk import get_current_context, task
from airflow.sdk.exceptions import AirflowFailException

logger = logging.getLogger(__name__)


def runner_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("CAPTURE_RUNNER_TOKEN", "")
    if not token:
        raise RuntimeError("CAPTURE_RUNNER_TOKEN is not configured")
    base = os.environ.get("CAPTURE_RUNNER_URL", "http://capture-runner:8020").rstrip("/")
    request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    # Polling có thể thử lại trong giới hạn; tuyệt đối không phát lại POST khi chưa rõ kết quả.
    attempts = 6 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=5 if method == "GET" else 15) as response:
                return json.loads(response.read(64 * 1024))
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt + 1 == attempts:
                raise
        logger.warning("Runner transient request failure; method=%s attempt=%s", method, attempt + 1)
        time.sleep(min(0.5 * (attempt + 1), 1))


@task(do_xcom_push=False)
def execute_capture_step(name: str):
    context = get_current_context()
    conf = context["dag_run"].conf or {}
    run_id, org = conf.get("run_id", ""), conf.get("org_id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", org):
        raise ValueError("Invalid capture pipeline context")
    path = f"/runs/{run_id}/steps/{name}"
    result = runner_request("POST", path, {"org_id": org, "attempt": context["ti"].try_number})
    deadline = time.monotonic() + 1500
    while result["status"] == "running":
        if time.monotonic() > deadline:
            raise TimeoutError("Collector task execution deadline exceeded")
        time.sleep(2)
        result = runner_request("GET", path + "?" + urlencode({"org_id": org}))
        heartbeat = result.get("heartbeat_at")
        if heartbeat and (datetime.now(UTC) - datetime.fromisoformat(heartbeat)).total_seconds() > 60:
            raise RuntimeError("Collector task heartbeat expired")
    if result["status"] not in ("succeeded", "skipped"):
        raise RuntimeError(f"Collector step {name} failed: {result.get('error_code') or result['status']}")
    if name == "finalize":
        # Finalizer có thể dọn thành công một pipeline lỗi; DAG vẫn phải hiện failed.
        final = runner_request("GET", path + "?" + urlencode({"org_id": org}))
        if final["pipeline_status"] != "succeeded":
            raise AirflowFailException(f"Capture pipeline ended as {final['pipeline_status']}")
