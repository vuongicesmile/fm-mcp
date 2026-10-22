"""Validation shared by collector tools."""

import re

_CONNECTION_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def connection_path(connection_id: str) -> str:
    if not _CONNECTION_ID.fullmatch(connection_id):
        raise ValueError("connection_id must be a lowercase Titan connection identifier")
    return f"/connections/{connection_id}"
