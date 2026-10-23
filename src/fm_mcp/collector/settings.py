"""Cấu hình nội bộ collector; không dùng database workflow FM để lưu capture."""

import os


def pg_options() -> dict:
    dsn = os.getenv("CAPTURE_PG_DSN", os.getenv("BMS_PG_DSN", ""))
    if dsn:
        return {"conninfo": dsn, "connect_timeout": 5}
    return {
        "host": os.getenv("CAPTURE_PG_HOST", os.getenv("BMS_PG_HOST", "localhost")),
        "port": int(os.getenv("CAPTURE_PG_PORT", os.getenv("BMS_PG_PORT", "5432"))),
        "dbname": os.getenv("CAPTURE_PG_DATABASE", os.getenv("BMS_PG_DATABASE", "control_plane")),
        "user": os.getenv("CAPTURE_PG_USER", os.getenv("POSTGRES_USER", "titan")),
        "password": os.getenv("CAPTURE_PG_PASSWORD", os.getenv("POSTGRES_PASSWORD", "titan-dev")),
        "connect_timeout": 5,
    }
