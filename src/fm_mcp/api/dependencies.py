"""Authentication and request dependencies for the Workflow Automation API."""

from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, status

from fm_mcp.api.settings import api_settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    roles: frozenset[str]


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_authenticated_user_id: str | None = Header(default=None),
    x_authenticated_roles: str | None = Header(default=None),
) -> CurrentUser:
    """Use a signed JWT in deployed environments; header identity is development-only."""
    if authorization and authorization.startswith("Bearer ") and api_settings.auth_jwt_secret:
        try:
            claims = jwt.decode(
                authorization.removeprefix("Bearer "),
                api_settings.auth_jwt_secret,
                algorithms=[api_settings.auth_jwt_algorithm],
                audience=api_settings.workflow_api_audience,
            )
        except jwt.PyJWTError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from error
        subject = claims.get("sub")
        if isinstance(subject, str) and subject:
            roles = claims.get("roles", [])
            return CurrentUser(subject, frozenset(roles if isinstance(roles, list) else []))
    if api_settings.environment == "development" and x_authenticated_user_id:
        roles = frozenset((x_authenticated_roles or "").split(",")) - {""}
        return CurrentUser(x_authenticated_user_id, roles)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


def require_role(*roles: str):
    async def dependency(user: CurrentUser = __import__("fastapi").Depends(get_current_user)) -> CurrentUser:
        if not user.roles.intersection(roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return dependency
