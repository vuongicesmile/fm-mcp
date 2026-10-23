"""Client Airflow REST v2; credential không rời phía backend."""

from __future__ import annotations

import os
import time

import httpx

from .definition import DAG_ID


class AirflowUnavailable(RuntimeError):
    pass


class AirflowClient:
    def __init__(self):
        self.base = os.environ.get("TITAN_AIRFLOW_URL", "http://localhost:8080").rstrip("/")
        self.token = os.environ.get("TITAN_AIRFLOW_TOKEN", "")
        self.expires = float("inf") if self.token else 0

    def _headers(self, client):
        if time.monotonic() >= self.expires:
            response = client.post(self.base + "/auth/token", json={
                "username": os.environ.get("TITAN_AIRFLOW_USER", "airflow"),
                "password": os.environ.get("TITAN_AIRFLOW_PASSWORD", ""),
            })
            response.raise_for_status()
            self.token = response.json()["access_token"]
            self.expires = time.monotonic() + 240
        return {"Authorization": f"Bearer {self.token}"}

    def submit(self, run: dict):
        try:
            with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
                headers = self._headers(client)
                run_id = f"capture__{run['id']}"
                response = client.post(self.base + f"/api/v2/dags/{DAG_ID}/dagRuns", headers=headers,
                                       json={"dag_run_id": run_id, "logical_date": None,
                                             "conf": {"run_id": run["id"], "org_id": run["org_id"]}})
                if response.status_code == 409:
                    # Mất response POST trước đó: xác nhận chính run đã tồn tại, không dispatch lần hai.
                    response = client.get(self.base + f"/api/v2/dags/fm_data_capture/dagRuns/{run_id}", headers=headers)
                response.raise_for_status()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise AirflowUnavailable("Airflow chưa nhận được pipeline; hệ thống sẽ thử dispatch lại") from exc

    def ready(self) -> bool:
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(self.base + "/api/v2/monitor/health")
                response.raise_for_status()
                health = response.json()
                if not all(health.get(name, {}).get("status") == "healthy" for name in ("metadatabase", "scheduler", "dag_processor")):
                    return False
                response = client.get(self.base + f"/api/v2/dags/{DAG_ID}", headers=self._headers(client))
                response.raise_for_status()
                dag = response.json()
                return not dag.get("is_paused", True) and not dag.get("has_import_errors", True)
        except (httpx.HTTPError, ValueError, KeyError):
            return False

    def state(self, run: dict) -> str:
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get(self.base + f"/api/v2/dags/fm_data_capture/dagRuns/capture__{run['id']}",
                                      headers=self._headers(client))
                response.raise_for_status()
                return response.json()["state"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise AirflowUnavailable("Không đọc được trạng thái Airflow") from exc
