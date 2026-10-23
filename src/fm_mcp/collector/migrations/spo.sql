CREATE SCHEMA IF NOT EXISTS spo;
CREATE TABLE IF NOT EXISTS spo.jobs (
    id text PRIMARY KEY,
    org_id text NOT NULL,
    connection_id text NOT NULL,
    request_key text NOT NULL,
    config jsonb NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    owner text,
    attempt integer NOT NULL DEFAULT 0,
    cancel_requested boolean NOT NULL DEFAULT false,
    manifest jsonb,
    result jsonb,
    error text,
    UNIQUE(org_id, connection_id, request_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS spo_one_active_connection ON spo.jobs(org_id,connection_id)
WHERE status IN ('queued','capturing','captured','loading');
CREATE INDEX IF NOT EXISTS spo_jobs_dispatch ON spo.jobs(status, created_at);
ALTER TABLE spo.jobs ADD COLUMN IF NOT EXISTS execution_backend text NOT NULL DEFAULT 'local';
CREATE TABLE IF NOT EXISTS spo.worker_health (
    id text PRIMARY KEY, heartbeat_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS spo.checkpoints (org_id text NOT NULL, connection_id text NOT NULL, identity text NOT NULL, etag text NOT NULL, PRIMARY KEY(org_id,connection_id,identity));
