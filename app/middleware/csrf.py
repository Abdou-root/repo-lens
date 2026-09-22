"""
CSRF Protection Middleware

Implements Cross-Site Request Forgery protection for state-changing operations.
Uses double-submit cookie pattern with synchronizer tokens.
"""

import secrets
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.responses import Response
from app.middleware.utils import should_skip_response_modification


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware that implements CSRF protection using double-submit cookie pattern.

    How it works:
    1. Generate a CSRF token and set it as a cookie (readable by JavaScript)
    2. Client must include the same token in X-CSRF-Token header for state-changing requests
    3. Middleware validates that cookie and header match

    Exempted endpoints:
    - /api/auth/* (already protected by OAuth state token)
    - GET, HEAD, OPTIONS requests (safe methods)
    """

    def __init__(self, app: ASGIApp, exempt_paths: list[str] | None = None, is_production: bool = False):
        super().__init__(app)
        self.exempt_paths = exempt_paths or ["/api/auth/"]

        # Paths that return streaming responses
        self.streaming_paths = [
            "/api/chat/stream",
            "/api/repos/",  # Covers /api/repos/{id}/events
        ]

        self.is_production = is_production

    def is_exempt(self, path: str) -> bool:
        """Check if the path is exempt from CSRF protection."""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)

    def is_streaming_path(self, path: str) -> bool:
        """Check if the path returns a streaming response."""
        return any(path.startswith(streaming) for streaming in self.streaming_paths)

    def generate_csrf_token(self) -> str:
        """Generate a cryptographically secure CSRF token."""
        return secrets.token_urlsafe(32)

    async def dispatch(self, request: Request, call_next):
        # Only check CSRF for state-changing methods
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            # Skip CSRF check for exempted paths
            if not self.is_exempt(request.url.path):
                # Skip CSRF check if request has Bearer token (Authorization header)
                # Bearer token auth doesn't need CSRF protection because tokens
                # are not automatically sent by browsers like cookies are
                auth_header = request.headers.get("Authorization", "")
                has_bearer_token = auth_header.startswith("Bearer ")

                if not has_bearer_token:
                    # Only validate CSRF for cookie-based auth
                    csrf_cookie = request.cookies.get("csrf_token")
                    csrf_header = request.headers.get("X-CSRF-Token")

                    # Validate CSRF token
                    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                        raise HTTPException(
                            status_code=403,
                            detail="CSRF token validation failed. Please refresh the page and try again.",
                        )

        # Process the request
        response: Response = await call_next(request)

        # Skip response modifications for:
        # - StreamingResponse (can't set cookies on streaming responses)
        # - Redirects (3xx) (Firefox compatibility)
        # - Known streaming endpoints (optimization)
        if should_skip_response_modification(response) or self.is_streaming_path(request.url.path):
            return response

        # Set CSRF token cookie if not present (non-streaming responses only)
        if "csrf_token" not in request.cookies:
            csrf_token = self.generate_csrf_token()
            response.set_cookie(
                key="csrf_token",
                value=csrf_token,
                httponly=False,  # Must be readable by JavaScript
                secure=True,  # Required for samesite="none"
                samesite="none",  # Allow cross-origin (Netlify -> Render)
                max_age=86400,  # 24 hours
            )

        return response
