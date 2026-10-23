# Collector Orchestration Service

Service đứng sau nhóm MCP collector, chạy bằng `fm-collector-api` trên cổng nội bộ
8021. Không sinh mã DAG từ chat và không import `titan_runtime`, dlt hoặc dbt.

## Đọc code

| Module | Trách nhiệm |
|---|---|
| `tools/collector/` | Sync, test, status, history, cancel, retry |
| `clients/collector_api.py` | MCP gọi service, không gọi Capture API của CP |
| `collector/api.py` | Contract API operator và API worker riêng |
| `collector/service.py` | Use cases, atomic enqueue/outbox và replay Bronze |
| `collector/source_jobs.py` | Repository source BMS/SPO dùng chung implementation |
| `collector/repository.py` | Pipeline/attempt/event, fencing và public redaction |
| `collector/dispatcher.py` | Dispatch pending và đối soát DAG |
| `collector/airflow_client.py` | Adapter Airflow REST với stable run ID |
| `collector/definition.py` | Danh sách bước và retry policy duy nhất |
| `collector/airflow_tasks.py` | Airflow gọi worker, đợi status và kiểm tra heartbeat |
| `orchestration/airflow/dags/fm_data_capture.py` | Template DAG mỏng |

## API và token

`/internal/tenants/{org}` dùng `FM_COLLECTOR_SERVICE_TOKEN`: health,
`connections/{id}/test`, `/sync`, `/sync/retry`, `/capture/status`, `/capture/jobs`,
`/capture/cancel`; `pipelines` hỗ trợ list/detail/events/cancel/retry.
Tool chỉ nhận identifier/request_key, không nhận source config tùy ý.

`/internal/worker/{org}/runs/{id}` dùng `CAPTURE_RUNNER_TOKEN` riêng:
private context, begin, pulse, finish, output, complete, cancel.
Operator token không đọc API worker; cả hai nhóm kiểm tra tenant binding.

Service đọc snapshot từ CP bằng `FM_COLLECTOR_CONTEXT_TOKEN` qua endpoint chỉ đọc
`/api/internal/collector-context/{org}/{connection}`. Không gọi route Sync của CP.
Không trả source config, token, context hoặc step output qua MCP/public API.

## Lifecycle

1. Sync đọc cấu hình đã validate từ CP qua backchannel.
2. Tạo source job và pipeline outbox trong cùng transaction PostgreSQL.
3. Dispatch DAG run `capture__<run_id>`; mất response không mở lượt thu thứ hai.
4. Airflow gọi Titan worker; worker báo heartbeat/progress và kết quả về service.
5. UI/agent đọc qua cùng nhóm MCP tool.
6. Retry tạo run mới liên kết run cũ và giữ capture ID; không tự retry capture BMS.

Thứ tự bước và retry xem `definition.py`. SPO chỉ ghi checkpoint sau toàn pipeline
thành công. Hủy dừng tại điểm an toàn và không xóa Bronze.

## Deployment và chuyển đổi

- Compose FM có service `collector`, nối network Titan mặc định `titan-data_default`.
- Bundle Titan có service `fm-collector` từ source/image FM, không có implementation thứ hai.
- Airflow mount DAG và helper từ repo này, không cần cài FastMCP trong scheduler.
- Schema `bms`, `spo`, `capture` vẫn ở capture PostgreSQL, không chuyển sang database workflow FM.
- Dừng dispatcher CP và worker legacy trước khi chuyển; giữ metadata, Bronze và checkpoint.
- Rollback đồng bộ FM service, worker client và DAG mount, chỉ khi không còn run hoạt động.
- Mọi credential lấy từ env/secret manager. Không dùng token demo trong production.

Xem thêm `.env.example` và runbook `docs/COLLECTOR_AIRFLOW.vi.md` ở Titan Data.
