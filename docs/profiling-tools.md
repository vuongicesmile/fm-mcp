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

`run_data_profiling` and `seed_data_profiling_demo` must be placed in the
Control Plane MCP profile's `write_tools` list. This makes the gateway require
an explicit confirmation before it dispatches either operation.

## Tool surface

| Tool | Purpose |
| --- | --- |
| `list_data_profiling_assets` | Discover raw BMS/SPO assets in the configured schema. |
| `run_data_profiling` | Calculate completeness, duplicates and IQR signals, then persist a run. |
| `get_data_profiling_run` | Read one persisted run. |
| `get_data_profiling_overview` | Aggregate the latest run per asset for Bronze, Silver or Gold. |
| `get_masked_raw_sample` | Return a bounded PII-masked source sample. |
| `seed_data_profiling_demo` | Persist explicitly labelled local demo findings. |

The profile service accepts only catalog-derived tables and quoted identifiers.
User input cannot supply raw SQL or arbitrary schemas.
