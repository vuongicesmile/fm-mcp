"""Dispatch outbox và đối soát DAG thuộc collector service, không chạy trong CP."""

import logging
import os
import threading
import time
from datetime import UTC, datetime

import httpx

from .airflow_client import AirflowUnavailable

logger = logging.getLogger(__name__)


class CollectorDispatcher:
    def __init__(self, service):
        self.service = service
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="collector-dispatch")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)

    def run(self):
        last_reconcile = 0.0
        while not self.stop.wait(5):
            try:
                for run in self.service.repository.pending():
                    self.service.dispatch(run)
                if time.monotonic() - last_reconcile > 30:
                    last_reconcile = time.monotonic()
                    self.reconcile()
            except Exception as exc:  # noqa: BLE001 -- dispatcher phải sống qua lỗi metadata tạm thời
                logger.warning("collector.dispatch_unavailable", extra={"error_type": type(exc).__name__})

    def reconcile(self):
        for run in self.service.repository.active():
            try:
                if self.service.scheduler.state(run) not in ("failed", "success"):
                    continue
                latest = {step["name"]: step for step in run["steps"]}
                if any(s["status"] == "running" and s["heartbeat_at"] and
                       (datetime.now(UTC) - s["heartbeat_at"]).total_seconds() < 65 for s in latest.values()):
                    continue
                with httpx.Client(timeout=5, trust_env=False) as client:
                    response = client.post(os.environ.get("CAPTURE_RUNNER_URL", "http://capture-runner:8020").rstrip("/")
                                           + f"/runs/{run['id']}/steps/finalize",
                                           headers={"Authorization": f"Bearer {os.environ.get('CAPTURE_RUNNER_TOKEN', '')}"},
                                           json={"org_id": run["org_id"], "attempt": latest.get("finalize", {}).get("attempt", 0) + 1})
                    response.raise_for_status()
            except (AirflowUnavailable, httpx.HTTPError):
                logger.warning("collector.reconcile_unavailable", extra={"run_id": run["id"]})
