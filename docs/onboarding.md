# Hướng dẫn đọc code FM Workflow Automation

Tài liệu này dành cho người mới vào repository. Hãy đọc theo thứ tự: entry
point → router → service → model → worker. MCP không mở database; mọi business
rule nằm ở API service.

## 1. Bản đồ source code

```mermaid
flowchart TB
    Main[src/fm_mcp/api/main.py<br/>Tạo FastAPI app] --> Routers[src/fm_mcp/api/routers/<br/>Nhận HTTP, validate schema]
    Routers --> Auth[src/fm_mcp/api/dependencies.py<br/>Đọc JWT / identity dev]
    Routers --> Services[src/fm_mcp/domain/services/<br/>Business rules + transaction]
    Services --> Models[src/fm_mcp/domain/models/workflow.py<br/>SQLAlchemy table mapping]
    Services --> DB[src/fm_mcp/infrastructure/database.py<br/>Async engine + session]
    DB --> PG[(fm_central)]

    MCPMain[src/fm_mcp/server.py] --> Tools[src/fm_mcp/tools/registry.py]
    Tools --> Client[src/fm_mcp/clients/fm_api.py]
    Client --> Routers

    Scheduler[scripts/evaluate_escalations.py] --> Escalation[NotificationService.evaluate_escalations]
    Dispatcher[scripts/dispatch_notifications.py] --> Delivery[NotificationDeliveryWorker]
    Delivery --> SMTP[SMTPEmailSender]
```

| Nơi đọc | Mục đích | Khi cần sửa |
|---|---|---|
| `api/main.py` | Đăng ký router và tạo app. | Thêm một nhóm endpoint mới. |
| `api/routers/` | HTTP method, URL, Pydantic request/response, quyền truy cập cơ bản. | Thay REST contract. |
| `api/dependencies.py` | Chuyển JWT/header thành `CurrentUser`. | Thay identity provider hoặc RBAC. |
| `domain/services/` | Quy tắc nghiệp vụ và atomic transaction. | Thay workflow, approval, risk, notification. |
| `domain/models/workflow.py` | Tên table, FK, index, constraint, relationship. | Thay database model kèm migration. |
| `schemas/` | Kiểm tra dữ liệu đầu vào và shape response. | Thêm field vào API. |
| `tools/registry.py` | MCP tool mỏng gọi REST. | Expose endpoint an toàn cho MCP. |
| `scripts/` | Worker tin cậy chạy từ scheduler/container. | Tác vụ nền, không phải public API. |

## 2. Luồng tạo và gửi request

```mermaid
sequenceDiagram
    actor R as Requester
    participant P as Portal / MCP
    participant A as Workflow API
    participant D as fm_central

    R->>P: Điền request
    P->>A: POST /api/v1/requests + JWT
    A->>A: Lấy CurrentUser, không tin requester_id từ body
    A->>D: INSERT fm_requests (draft)
    A->>D: INSERT status_history + audit_log
    A-->>P: Request draft

    R->>P: Submit
    P->>A: POST /requests/{id}/submit
    A->>D: Lock request row
    A->>D: Tạo fm_approval_steps và assignments
    A->>D: Update request = in_review
    A->>D: Ghi history, audit, notification
    A-->>P: Request in_review
```

## 3. Luồng approval tuần tự và `any` / `all`

```mermaid
sequenceDiagram
    actor U as Approver
    participant A as Approval API
    participant S as ApprovalService
    participant D as PostgreSQL

    U->>A: POST /approvals/{stepId}/approve<br/>Idempotency-Key
    A->>S: actor_id + roles từ JWT
    S->>D: SELECT step FOR UPDATE
    S->>D: Kiểm tra step trước đã approved/skipped
    S->>D: Kiểm tra assignment hoặc approver role
    alt approval_mode = any
        S->>D: Approve actor, skip assignment còn lại
        S->>D: Mark step approved
    else approval_mode = all
        S->>D: Approve assignment của actor
        alt còn người chưa approve
            S->>D: Giữ step in_progress
        else tất cả đã approve
            S->>D: Mark step approved
        end
    end
    alt không còn step pending
        S->>D: Request = approved + history + notification
    end
    S-->>A: Result
    A-->>U: Approval result
```

`conditions.approver_ids` trên workflow step chứa các user ID đã được Control
Plane/organizational service resolve. Khi danh sách này trống, API kiểm tra role
đã xác thực thay vì nhận `approver_id` từ client.

## 4. Luồng email an toàn và có retry

```mermaid
sequenceDiagram
    actor Admin as FM admin / trusted MCP
    participant API as Workflow API
    participant DB as fm_notifications
    participant W as Dispatcher worker
    participant SMTP as Mailpit / SMTP relay
    participant E as Email recipient

    Admin->>API: POST /notifications (channel=email)
    API->>API: Validate recipient_address và template
    API->>DB: INSERT status=pending
    W->>DB: Lock one due email (SKIP LOCKED)
    W->>DB: status=sending, attempt_count + 1
    W->>SMTP: SMTP send rendered subject/body
    alt SMTP success
        SMTP->>E: Email
        W->>DB: status=sent, sent_at
    else SMTP failure
        W->>DB: status=failed, last_error, scheduled_at + retry delay
    end
```

Worker gửi email **sau** khi transaction queue đã commit. Vì vậy người dùng không
nhận email trùng chỉ vì request HTTP retry; delivery state được nhìn thấy trong
`fm_notifications`.

## 5. Function map

| Module / function | Làm gì | Điều không làm |
|---|---|---|
| `WorkflowService.create_request` | Tạo request draft, status history, audit. | Không nhận requester ID từ client. |
| `WorkflowService.submit` | Khóa request, tạo approval steps/assignments, queue notification. | Không approve request. |
| `WorkflowService.close` | Đóng request đã approved. | Không cho đóng draft/in_review. |
| `ApprovalService.pending` | Lọc step mà current user đủ điều kiện xử lý. | Không expose step không tuần tự. |
| `ApprovalService.act` | Lock step/request, xử lý idempotency và action. | Không cho approve thay người khác. |
| `RiskService.assess` | Lưu likelihood/impact/score và audit. | Không tự thay ownership request. |
| `NotificationService.queue` | Lưu notification outbox record. | Không gọi SMTP trong HTTP request. |
| `NotificationService.evaluate_escalations` | Tạo reminder duy nhất cho step/rule/time quá hạn. | Không có public manual endpoint. |
| `NotificationDeliveryWorker.run_once` | Claim email, gửi SMTP, cập nhật sent/failed. | Không gửi `in_app` record qua SMTP. |
| `SMTPEmailSender.send` | Render MIME message và gọi SMTP relay. | Không ghi password SMTP vào log. |
| `tools.registry._call` | Forward MCP call sang REST API với caller headers dev. | Không mở DB session. |

## 6. Checklist khi thêm chức năng

1. Cần bảng/field mới: sửa model **và** tạo Alembic migration mới của module.
2. Thêm Pydantic Create/Update/Read schema.
3. Đặt business rule ở `domain/services`, trong transaction và audit nếu là write.
4. Thêm router nhỏ chỉ lo HTTP/auth/response.
5. Nếu cần MCP, thêm thin tool vào `tools/registry.py`; không copy business rule.
6. Viết test với PostgreSQL test riêng; không chạy migration development lên production.
