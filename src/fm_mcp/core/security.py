"""Authentication and user-permission forwarding helpers."""


def build_auth_headers(access_token: str) -> dict[str, str]:
    """Build headers used to forward the caller identity to FM Backend."""
    return {"Authorization": f"Bearer {access_token}"}
