"""Metadata bền vững của pipeline; không lưu payload nguồn trong event/log công khai."""

from __future__ import annotations

import os
from contextlib import nullcontext
from urllib.parse import quote
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .definition import STEPS
from .settings import pg_options

TERMINAL = {"succeeded", "failed", "cancelled"}
PROGRESS_KEYS = {"files_done", "files_total", "bytes", "rows", "events", "seconds_elapsed", "seconds_total"}

DDL = """
CREATE SCHEMA IF NOT EXISTS capture;
CREATE TABLE IF NOT EXISTS capture.pipeline_runs (
 id text PRIMARY KEY, org_id text NOT NULL, connection_id text NOT NULL,
 connector text NOT NULL CHECK (connector IN ('bms','spo')), capture_id text NOT NULL,
 context jsonb NOT NULL, status text NOT NULL DEFAULT 'queued',
 dispatch_status text NOT NULL DEFAULT 'pending', dispatch_error text,
 cancel_requested boolean NOT NULL DEFAULT false, retry_of text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS pipeline_active_connection ON capture.pipeline_runs(org_id,connection_id)
 WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS pipeline_tenant_time ON capture.pipeline_runs(org_id,created_at DESC);
CREATE TABLE IF NOT EXISTS capture.pipeline_steps (
 run_id text NOT NULL REFERENCES capture.pipeline_runs(id), name text NOT NULL, attempt integer NOT NULL,
 status text NOT NULL, token text, progress jsonb NOT NULL DEFAULT '{}', output jsonb NOT NULL DEFAULT '{}',
 error_code text, error text, started_at timestamptz, finished_at timestamptz, heartbeat_at timestamptz,
 PRIMARY KEY(run_id,name,attempt)
);
CREATE TABLE IF NOT EXISTS capture.pipeline_events (
 id bigserial PRIMARY KEY, run_id text NOT NULL REFERENCES capture.pipeline_runs(id),
 step text NOT NULL, attempt integer NOT NULL, kind text NOT NULL, message text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pipeline_events_run ON capture.pipeline_events(run_id,id);
"""


class PipelineConflict(ValueError):
    pass


class PipelineStore:
    def connect(self):
        return psycopg.connect(**pg_options(), row_factory=dict_row)

    def migrate(self):
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(748235)")
            db.execute(DDL)

    def create(self, job: dict, connector: str, context: dict, *, retry_of: str | None = None, transaction=None) -> dict:
        with nullcontext(transaction) if transaction is not None else self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"pipeline:{job['org_id']}:{job['connection_id']}",))
            active = db.execute("SELECT * FROM capture.pipeline_runs WHERE org_id=%s AND connection_id=%s "
                                "AND status IN ('queued','running') FOR UPDATE", (job["org_id"], job["connection_id"])).fetchone()
            if active:
                if active["capture_id"] == job["id"]:
                    return active
                raise PipelineConflict("Nguồn đang có pipeline chưa kết thúc")
            if not retry_of:
                previous = db.execute("SELECT * FROM capture.pipeline_runs WHERE capture_id=%s ORDER BY created_at DESC LIMIT 1",
                                      (job["id"],)).fetchone()
                if previous:
                    return previous
            run_id = uuid4().hex
            run = db.execute("INSERT INTO capture.pipeline_runs(id,org_id,connection_id,connector,capture_id,context,retry_of) "
                             "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                             (run_id, job["org_id"], job["connection_id"], connector, job["id"], Jsonb(context), retry_of)).fetchone()
            for name in STEPS:
                status = "skipped" if retry_of and name in ("validate_source", "capture") else "queued"
                db.execute("INSERT INTO capture.pipeline_steps(run_id,name,attempt,status) VALUES(%s,%s,0,%s)",
                           (run_id, name, status))
            return run

    def get(self, org: str, run_id: str, *, private: bool = False) -> dict:
        with self.connect() as db:
            run = db.execute("SELECT * FROM capture.pipeline_runs WHERE id=%s AND org_id=%s", (run_id, org)).fetchone()
            if not run:
                raise LookupError("Không tìm thấy pipeline")
            steps = db.execute("SELECT * FROM capture.pipeline_steps WHERE run_id=%s ORDER BY attempt", (run_id,)).fetchall()
            newest = db.execute("SELECT id FROM capture.pipeline_runs WHERE org_id=%s AND connection_id=%s "
                                "ORDER BY created_at DESC LIMIT 1", (org, run["connection_id"])).fetchone()
        run["steps"] = [step for name in STEPS for step in steps if step["name"] == name]
        latest = {step["name"]: step for step in run["steps"]}
        run["completed_steps"] = sum(s["status"] in ("succeeded", "skipped") for s in latest.values())
        run["total_steps"] = len(STEPS)
        run["current_step"] = next((name for name in STEPS if latest[name]["status"] in ("running", "failed")),
                                   next((name for name in STEPS if latest[name]["status"] == "queued"), None))
        run["execution_backend"] = "airflow"
        run["dag_id"] = "fm_data_capture"
        run["dag_run_id"] = f"capture__{run_id}"
        run["can_retry"] = bool(run["status"] == "failed" and newest["id"] == run_id
                                and latest["capture"]["status"] in ("succeeded", "skipped"))
        public_url = os.environ.get("TITAN_AIRFLOW_PUBLIC_URL", "http://localhost:8080").rstrip("/")
        run["airflow_url"] = f"{public_url}/dags/{run['dag_id']}/runs/{quote(run['dag_run_id'], safe='')}" if public_url else None
        if not private:
            run.pop("context")
            for step in run["steps"]:
                step.pop("token", None)
                step.pop("output", None)
        return run

    def list(self, org: str, *, connection: str = "", status: str = "", offset: int = 0, limit: int = 20):
        where, args = "org_id=%s", [org]
        for field, value in (("connection_id", connection), ("status", status)):
            if value:
                where += f" AND {field}=%s"
                args.append(value)
        with self.connect() as db:
            total = db.execute(f"SELECT count(*) AS n FROM capture.pipeline_runs WHERE {where}", args).fetchone()["n"]
            ids = db.execute(f"SELECT id FROM capture.pipeline_runs WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                             (*args, limit, offset)).fetchall()
        return {"items": [self.get(org, row["id"]) for row in ids], "total": total, "offset": offset, "limit": limit}

    def latest(self, org: str, capture_id: str):
        with self.connect() as db:
            row = db.execute("SELECT id FROM capture.pipeline_runs WHERE org_id=%s AND capture_id=%s ORDER BY created_at DESC LIMIT 1",
                             (org, capture_id)).fetchone()
        return self.get(org, row["id"]) if row else None

    def events(self, org: str, run_id: str, after: int = 0, limit: int = 100):
        self.get(org, run_id)
        with self.connect() as db:
            return db.execute("SELECT id,step,attempt,kind,message,created_at FROM capture.pipeline_events "
                              "WHERE run_id=%s AND id>%s ORDER BY id LIMIT %s", (run_id, after, limit)).fetchall()

    def pending(self):
        with self.connect() as db:
            return db.execute("SELECT id,org_id FROM capture.pipeline_runs WHERE dispatch_status='pending' "
                              "AND status IN ('queued','running') ORDER BY created_at LIMIT 20").fetchall()

    def active(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,org_id FROM capture.pipeline_runs WHERE dispatch_status='submitted' "
                              "AND status IN ('queued','running') ORDER BY updated_at LIMIT 20").fetchall()
        return [self.get(row["org_id"], row["id"]) for row in rows]

    def dispatched(self, run_id: str, error: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE capture.pipeline_runs SET dispatch_status=%s,dispatch_error=%s,updated_at=now() WHERE id=%s",
                       ("pending" if error else "submitted", error, run_id))

    def cancel(self, org: str, run_id: str):
        with self.connect() as db:
            db.execute("UPDATE capture.pipeline_runs SET cancel_requested=true,updated_at=now() WHERE id=%s AND org_id=%s "
                       "AND status IN ('queued','running')", (run_id, org))

    def begin(self, org: str, run_id: str, name: str, attempt: int) -> dict:
        if name not in STEPS:
            raise ValueError("Invalid pipeline step")
        with self.connect() as db:
            run = db.execute("SELECT * FROM capture.pipeline_runs WHERE id=%s AND org_id=%s FOR UPDATE", (run_id, org)).fetchone()
            if not run:
                raise LookupError("Pipeline not found")
            previous = db.execute("SELECT * FROM capture.pipeline_steps WHERE run_id=%s AND name=%s ORDER BY attempt DESC LIMIT 1",
                                  (run_id, name)).fetchone()
            if previous["status"] in ("succeeded", "skipped"):
                return previous
            if previous["status"] == "running":
                # Chỉ cho fencing mới sau khi heartbeat cũ hết hạn; BMS capture không được tự mở cửa sổ mới.
                alive = db.execute("SELECT %s::timestamptz > now()-interval '45 seconds' AS alive", (previous["heartbeat_at"],)).fetchone()["alive"]
                if alive:
                    return previous
                db.execute("UPDATE capture.pipeline_steps SET status='failed',error_code='WorkerInterrupted',"
                           "error='Tiến trình thực thi bị ngắt',finished_at=now() WHERE run_id=%s AND name=%s AND attempt=%s",
                           (run_id, name, previous["attempt"]))
                if name == "capture":
                    raise PipelineConflict("Capture interrupted; start a new synchronization")
            if run["status"] in TERMINAL:
                raise PipelineConflict("Pipeline already finished")
            if name != "finalize":
                if run["cancel_requested"]:
                    raise PipelineConflict("Pipeline cancellation requested")
                for before in STEPS[:STEPS.index(name)]:
                    row = db.execute("SELECT status FROM capture.pipeline_steps WHERE run_id=%s AND name=%s ORDER BY attempt DESC LIMIT 1",
                                     (run_id, before)).fetchone()
                    if row["status"] not in ("succeeded", "skipped"):
                        raise PipelineConflict("Previous pipeline step has not succeeded")
            if name == "capture" and previous["attempt"] > 0:
                raise PipelineConflict("Capture cannot be automatically retried")
            if previous["status"] == "failed" and attempt <= previous["attempt"]:
                return previous
            attempt = max(attempt, previous["attempt"] + 1)
            token = uuid4().hex
            step = db.execute("INSERT INTO capture.pipeline_steps(run_id,name,attempt,status,token,started_at,heartbeat_at) "
                              "VALUES(%s,%s,%s,'running',%s,now(),now()) RETURNING *", (run_id, name, attempt, token)).fetchone()
            db.execute("UPDATE capture.pipeline_runs SET status='running',updated_at=now() WHERE id=%s", (run_id,))
            db.execute("INSERT INTO capture.pipeline_events(run_id,step,attempt,kind,message) VALUES(%s,%s,%s,'started',%s)",
                       (run_id, name, attempt, f"Started {name}"))
            step["execute"] = True
            return step

    def pulse(self, run_id: str, name: str, token: str, progress: dict | None = None) -> bool:
        progress = {key: value for key, value in (progress or {}).items() if key in PROGRESS_KEYS and isinstance(value, (int, float))}
        with self.connect() as db:
            row = db.execute("UPDATE capture.pipeline_steps SET heartbeat_at=now(),progress=progress || %s WHERE run_id=%s "
                             "AND name=%s AND token=%s AND status='running' RETURNING run_id", (Jsonb(progress), run_id, name, token)).fetchone()
            run = db.execute("SELECT cancel_requested FROM capture.pipeline_runs WHERE id=%s", (run_id,)).fetchone()
            db.execute("UPDATE capture.pipeline_runs SET updated_at=now() WHERE id=%s", (run_id,))
        return bool(row and run and (name == "finalize" or not run["cancel_requested"]))

    def finish_step(self, run_id: str, step: dict, *, output: dict | None = None, error_code: str | None = None):
        status = "failed" if error_code else "skipped" if (output or {}).get("not_required") else "succeeded"
        message = f"{step['name']}: {error_code}" if error_code else f"Completed {step['name']}"
        with self.connect() as db:
            row = db.execute("UPDATE capture.pipeline_steps SET status=%s,output=%s,error_code=%s,error=%s,finished_at=now() "
                             "WHERE run_id=%s AND name=%s AND token=%s AND status='running' RETURNING run_id",
                             (status, Jsonb(output or {}), error_code, message if error_code else None, run_id, step["name"], step["token"])).fetchone()
            if not row:
                raise PipelineConflict("Pipeline step fencing token expired")
            db.execute("INSERT INTO capture.pipeline_events(run_id,step,attempt,kind,message) VALUES(%s,%s,%s,%s,%s)",
                       (run_id, step["name"], step["attempt"], status, message))

    def output(self, run_id: str, name: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT output FROM capture.pipeline_steps WHERE run_id=%s AND name=%s AND status='succeeded' "
                             "ORDER BY attempt DESC LIMIT 1", (run_id, name)).fetchone()
        return row["output"] if row else {}

    def complete(self, org: str, run_id: str) -> str:
        run = self.get(org, run_id)
        latest = {s["name"]: s for s in run["steps"]}
        status = "cancelled" if run["cancel_requested"] else "failed" if any(
            s["status"] not in ("succeeded", "skipped") for name, s in latest.items() if name != "finalize") else "succeeded"
        with self.connect() as db:
            db.execute("UPDATE capture.pipeline_steps SET status=%s WHERE run_id=%s AND status='queued'",
                       ("cancelled" if status == "cancelled" else "upstream_failed", run_id))
            db.execute("UPDATE capture.pipeline_steps SET status='failed',error_code='WorkerInterrupted',"
                       "error='Tiến trình thực thi bị ngắt',finished_at=now() WHERE run_id=%s AND name!='finalize' AND status='running'",
                       (run_id,))
            db.execute("UPDATE capture.pipeline_runs SET status=%s,finished_at=now(),updated_at=now() WHERE id=%s AND org_id=%s",
                       (status, run_id, org))
        return status
