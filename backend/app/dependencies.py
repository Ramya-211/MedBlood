"""
dependencies.py

FastAPI dependencies for authentication and role-based authorization.
Every protected endpoint declares `Depends(require_roles(...))`.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import Role
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False)


def get_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return creds.credentials


def get_current_user(token: str = Depends(get_token)) -> dict:
    try:
        return auth_service.resolve_user_from_token(token)
    except auth_service.AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e), headers={"WWW-Authenticate": "Bearer"})


def require_roles(*allowed: Role):
    allowed_values = {r.value for r in allowed}

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_values:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to access this resource.")
        return user

    return checker
