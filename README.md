# FM MCP Server

`fm-mcp` là repository của module Workflow Automation (EPIC 3). Module có một
FastAPI API sở hữu dữ liệu workflow trong `fm_central` và một FastMCP adapter
gọi API đó qua REST. FM Control Plane chỉ điều phối giữa các module.

Xem thiết kế chi tiết tại [docs/architecture.md](docs/architecture.md).

## Cài đặt

```bash
cp .env.example .env
pip install -e .
```

Workflow Automation API dùng `DATABASE_URL` để kết nối `fm_central`. MCP adapter
dùng `FM_WORKFLOW_API_URL`; nó không nhận database credentials.

`fm-mcp` có Alembic history riêng với version table `alembic_version_fm_mcp`.
Migration của module chỉ thao tác các bảng EPIC 3 mà module sở hữu.

## Chạy server

```bash
fm-mcp
```

## Test

Unit test mock HTTP client của API khi test MCP adapter. Integration test chạy
với PostgreSQL test database riêng và chỉ ở đó mới chạy migration của module.

## Migration

Các migration của EPIC 3 nằm trong `alembic/versions` và dùng version table
`alembic_version_fm_mcp`. Chỉ chạy chúng với database development/test riêng:

```bash
FM_ENV=test DATABASE_URL=postgresql+asyncpg://... ./scripts/migrate.sh
```

## Docker Compose development

```bash
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d api
docker compose run --rm mcp
```

`mcp` uses stdio. Trong local development, nó chuyển `FM_MCP_DEV_USER_ID` thành
identity header cho API; không dùng cấu hình này ở production.
## Extended services

EPIC 3 owns its Workflow Automation tables in `fm_central`. The FastAPI service
owns database access; FastMCP only calls the API over REST.

### Local run

```bash
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d api
```

The API is available at `http://localhost:8000`, with OpenAPI documentation at
`http://localhost:8000/docs`. Development authentication uses
`X-Authenticated-User-Id` and `X-Authenticated-Roles`; production requires a
validated JWT from the Control Plane.

### Services

- Workflow requests: draft, update, submit, close and immutable status history.
- Approvals: sequential `any`/`all` processing, database row locking and
  `Idempotency-Key` support. Person-level approvers come from
  `workflow_step.conditions.approver_ids`; otherwise the Control Plane role in
  the authenticated identity is used.
- Risk register: create/update, assessment, latest assessment and heatmap.
  The current score default is likelihood × impact on the existing 1–5 schema;
  confirm the RMIT matrix before production policy is enabled.
- Notifications: creates delivery records only. Email/Teams delivery must be
  performed by an existing adapter/worker, so delivery is not falsely treated
  as atomically committed with the database transaction.
- Escalation: call the trusted scheduler worker, never a public manual endpoint:

```bash
docker compose --profile tools run --rm scheduler
```

The database unique constraint makes repeated scans idempotent for an approval
step, escalation rule and scheduled time.
