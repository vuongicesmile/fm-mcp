# FM MCP data profiling

FM MCP owns RMIT FM data profiling. Titan Data Control Plane only authenticates,
authorizes, audits, and dispatches the MCP call; it does not receive warehouse
credentials or execute profiling SQL.

## Required configuration

```dotenv
FM_PROFILING_CLICKHOUSE_URL=http://clickhouse:8123
FM_PROFILING_CLICKHOUSE_USER=titan
FM_PROFILING_CLICKHOUSE_PASSWORD=<secret>
FM_PROFILING_RAW_SCHEMA=t_rmit_fm_raw
FM_PROFILING_ORG_ID=rmit_fm
```

`run_data_profiling`, `seed_data_profiling_demo` and `seed_bad_data_profiling_demo` must be placed in the
Control Plane MCP profile's `write_tools` list. This makes the gateway require
an explicit confirmation before it dispatches either operation.

## Tool surface

| Tool | Purpose |
| --- | --- |
| `get_bms_dashboard` | Đọc overview BMS từ Marts, chỉ lấy điểm đo Valid, trả biểu đồ/bộ lọc và link Portal. |
| `get_energy_comparison` | Demo development: so sánh điện (kWh) hoặc nước (m³) cùng số ngày hoàn tất; lọc building/equipment/object_type, nhóm building/equipment/object_type. Trả hai kỳ, chuỗi ngày, coverage, nhận xét và link biểu đồ. Không trộn đơn vị. |
| `list_data_profiling_assets` | Discover raw BMS/SPO assets in the configured schema. |
| `run_data_profiling` | Calculate completeness, duplicates and IQR signals, then persist a run. |
| `get_data_profiling_run` | Read one persisted run. |
| `get_data_profiling_overview` | Aggregate the latest run per asset for Bronze, Silver or Gold. |
| `get_masked_raw_sample` | Return a bounded PII-masked source sample. |
| `seed_data_profiling_demo` | Persist explicitly labelled local demo findings without changing Raw. |
| `seed_bad_data_profiling_demo` | Development-only Raw → Staging → Marts bad-data lab with real ClickHouse rows and quarantine summary. |

The profile service accepts only catalog-derived tables and quoted identifiers.
User input cannot supply raw SQL or arbitrary schemas.
