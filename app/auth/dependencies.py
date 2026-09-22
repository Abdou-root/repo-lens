import os
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.jwt_handler import verify_token
from typing import Optional, Dict, Any

security = HTTPBearer(auto_error=False)  # Don't auto-error, we'll check cookies too


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Dependency to optionally get current authenticated user.

    Returns None if not authenticated (doesn't raise exception).
    Useful for endpoints that allow both authenticated and unauthenticated access.
    """
    token = None

    # Try Authorization header first
    if credentials:
        token = credentials.credentials
    # Fall back to cookie
    elif "auth_token" in request.cookies:
        token = request.cookies.get("auth_token")

    if not token:
        return None

    payload = verify_token(token)
    return payload  # May be None if token is invalid


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user.

    Checks for token in:
    1. Authorization header (Bearer token)
    2. auth_token cookie (httpOnly)

    Raises 401 if not authenticated.
    """
    token = None

    # Try Authorization header first
    if credentials:
        token = credentials.credentials
    # Fall back to cookie
    elif "auth_token" in request.cookies:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency to verify user has admin privileges.

    Checks if user's GitHub ID is in ADMIN_GITHUB_IDS environment variable.
    In development, allows all authenticated users if no admins configured.
    """
    admin_ids = os.getenv("ADMIN_GITHUB_IDS", "").split(",")
    admin_ids = [id.strip() for id in admin_ids if id.strip()]

    if not admin_ids:
        # In development, allow if no admins configured
        if os.getenv("APP_ENV", "development") != "production":
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access not configured"
        )

    if str(current_user.get("github_id")) not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user