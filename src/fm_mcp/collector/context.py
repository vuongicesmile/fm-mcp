"""Đọc cấu hình/snapshot qua backchannel; không gọi endpoint khởi chạy của Titan."""

import os

import httpx


def source_context(org: str, connection: str, *, snapshot: bool = False) -> dict:
    token = os.environ.get("FM_COLLECTOR_CONTEXT_TOKEN", "")
    if not token:
        raise RuntimeError("Collector context credential is not configured")
    base = os.environ.get("FM_COLLECTOR_CONTROL_PLANE_URL", "http://host.docker.internal:8000").rstrip("/")
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        response = client.get(f"{base}/api/internal/collector-context/{org}/{connection}",
                              params={"snapshot": str(snapshot).lower()}, headers={"X-Collector-Context-Token": token})
        response.raise_for_status()
        return response.json()
