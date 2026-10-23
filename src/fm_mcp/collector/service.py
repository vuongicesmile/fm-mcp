"""Use cases collector: Sync, trạng thái, hủy và replay Bronze; không chứa dlt/dbt."""

import os

import httpx

from .airflow_client import AirflowClient, AirflowUnavailable
from .context import source_context
from .repository import PipelineStore
from .source_jobs import SourceJobs


class CollectorService:
    def __init__(self, repository=None, scheduler=None, contexts=source_context):
        self.repository = repository or PipelineStore()
        self.scheduler = scheduler or AirflowClient()
        self.contexts = contexts

    def migrate(self):
        self.repository.migrate()
        for name in ("bms", "spo"):
            SourceJobs(name).migrate()

    def source(self, org, connection, *, snapshot=False):
        data = self.contexts(org, connection, snapshot=snapshot)
        return data, SourceJobs(data["connector"])

    def dispatch(self, run):
        try:
            self.scheduler.submit(run)
            self.repository.dispatched(run["id"])
        except AirflowUnavailable:
            self.repository.dispatched(run["id"], "Đang chờ Airflow; lượt chạy đã được lưu")

    def public_job(self, org, job):
        if job is None:
            return None
        run = self.repository.latest(org, job["id"])
        fields = ("id", "status", "created_at", "updated_at", "attempt", "error", "result", "cancel_requested")
        return {**{key: job[key] for key in fields}, "pipeline_id": run["id"] if run else None,
                "can_retry_load": bool(run and run["can_retry"] and job["manifest"])}

    def sync(self, org, connection, key):
        context, source = self.source(org, connection, snapshot=True)
        if not context["enabled"] or context.get("paused"):
            raise ValueError("Nguồn chưa bật hoặc đang tạm dừng")
        with source.connect() as db:
            job = source.enqueue(org, connection, key, context["config"], db)
            run = self.repository.create(job, source.connector, context["context"], transaction=db)
        self.dispatch(run)
        return self.public_job(org, job)

    def status(self, org, connection):
        context, source = self.source(org, connection)
        return {"enabled": context["enabled"], "worker_ready": self.ready(),
                "job": self.public_job(org, source.latest(org, connection))}

    def history(self, org, connection, limit):
        context, source = self.source(org, connection)
        return {"enabled": context["enabled"], "worker_ready": self.ready(),
                "jobs": [self.public_job(org, job) for job in source.list(org, connection, limit)]}

    def ready(self):
        if not self.scheduler.ready():
            return False
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                return client.get(os.environ.get("CAPTURE_RUNNER_URL", "http://capture-runner:8020").rstrip("/") + "/health",
                                  headers={"Authorization": "Bearer " + os.environ.get("CAPTURE_RUNNER_TOKEN", "")}).is_success
        except httpx.HTTPError:
            return False

    def cancel_run(self, org, identity):
        run = self.repository.get(org, identity)
        if run["status"] not in ("queued", "running"):
            raise ValueError("Lượt chạy đã kết thúc; không thể hủy")
        self.repository.cancel(org, identity)
        SourceJobs(run["connector"]).cancel(org, run["connection_id"], run["capture_id"])
        return {"ok": True}

    def cancel(self, org, connection):
        _, source = self.source(org, connection)
        job = source.latest(org, connection)
        run = self.repository.latest(org, job["id"]) if job else None
        if run and run["status"] in ("queued", "running"):
            return self.cancel_run(org, run["id"])
        return {"ok": True}

    def retry(self, org, connection, identity=None):
        _, source = self.source(org, connection)
        job = source.latest(org, connection)
        previous = self.repository.latest(org, job["id"]) if job else None
        if not previous or not previous["can_retry"] or (identity and previous["id"] != identity):
            raise ValueError("Chỉ nạp lại pipeline lỗi mới nhất đã có Bronze")
        context = self.repository.get(org, previous["id"], private=True)["context"]
        with source.connect() as db:
            job = source.retry(org, connection, db)
            run = self.repository.create(job, source.connector, context, retry_of=previous["id"], transaction=db)
        self.dispatch(run)
        return self.repository.get(org, run["id"])
