"""Một repository lifecycle cho BMS/SPO; worker giữ lease theo schema hiện có."""

from uuid import uuid4

from psycopg.types.json import Jsonb

from .repository import PipelineStore

ACTIVE = ("queued", "capturing", "captured", "loading")


class SourceJobs:
    def __init__(self, connector: str):
        if connector not in ("bms", "spo"):
            raise ValueError("Unsupported collector connector")
        self.connector = connector
        self.table = f"{connector}.jobs"

    def connect(self):
        return PipelineStore().connect()

    def migrate(self):
        from importlib.resources import files
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(748233)")
            db.execute(files("fm_mcp.collector").joinpath(f"migrations/{self.connector}.sql").read_text())

    def enqueue(self, org, connection, key, config, db):
        db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{self.connector}:{org}:{connection}",))
        previous = db.execute(f"SELECT * FROM {self.table} WHERE org_id=%s AND connection_id=%s AND request_key=%s",
                              (org, connection, key)).fetchone()
        if previous:
            if previous["execution_backend"] != "airflow":
                raise ValueError("Request key belongs to a legacy synchronization")
            return previous
        if db.execute(f"SELECT 1 FROM {self.table} WHERE org_id=%s AND connection_id=%s AND status=ANY(%s)",
                      (org, connection, list(ACTIVE))).fetchone():
            raise ValueError("Nguồn đang có lượt đồng bộ chưa kết thúc")
        return db.execute(f"INSERT INTO {self.table}(id,org_id,connection_id,request_key,config,execution_backend) "
                          "VALUES(%s,%s,%s,%s,%s,'airflow') RETURNING *", (uuid4().hex, org, connection, key, Jsonb(config))).fetchone()

    def latest(self, org, connection):
        with self.connect() as db:
            return db.execute(f"SELECT * FROM {self.table} WHERE org_id=%s AND connection_id=%s ORDER BY created_at DESC LIMIT 1",
                              (org, connection)).fetchone()

    def list(self, org, connection, limit):
        with self.connect() as db:
            return db.execute(f"SELECT * FROM {self.table} WHERE org_id=%s AND connection_id=%s ORDER BY created_at DESC LIMIT %s",
                              (org, connection, limit)).fetchall()

    def cancel(self, org, connection, job_id=None):
        with self.connect() as db:
            db.execute(f"UPDATE {self.table} SET cancel_requested=true,status=CASE WHEN status IN ('queued','captured') "
                       "THEN 'cancelled' ELSE status END,updated_at=now() WHERE org_id=%s AND connection_id=%s "
                       "AND status=ANY(%s) AND (%s::text IS NULL OR id=%s)", (org, connection, list(ACTIVE), job_id, job_id))

    def retry(self, org, connection, db):
        db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{self.connector}:{org}:{connection}",))
        row = db.execute(f"SELECT * FROM {self.table} WHERE org_id=%s AND connection_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                         (org, connection)).fetchone()
        if not row or row["status"] != "failed" or not row["manifest"] or row["execution_backend"] != "airflow":
            raise ValueError("Không có batch lỗi đã lưu Bronze để nạp lại")
        return db.execute(f"UPDATE {self.table} SET status='captured',cancel_requested=false,error=NULL,updated_at=now() "
                          "WHERE id=%s RETURNING *", (row["id"],)).fetchone()
