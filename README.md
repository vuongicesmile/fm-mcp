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
