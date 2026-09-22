"""
Security Headers Middleware

Adds security-related HTTP headers to all responses to protect against
common web vulnerabilities like XSS, clickjacking, and MIME type sniffing.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.middleware.utils import should_skip_response_modification


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all HTTP responses.

    Headers added:
    - Content-Security-Policy: Prevents XSS and data injection attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Enables browser XSS filtering
    - Strict-Transport-Security: Enforces HTTPS (production only)
    - Referrer-Policy: Controls referrer information
    """

    def __init__(self, app: ASGIApp, is_production: bool = False):
        super().__init__(app)
        self.is_production = is_production

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Skip security headers for:
        # - StreamingResponse (headers not applicable/can interfere with streaming)
        # - Redirects (3xx) (Firefox compatibility - CSP on redirects causes errors)
        if should_skip_response_modification(response):
            return response

        # Build connect-src based on environment
        # In development, allow localhost HTTP connections for API calls
        if self.is_production:
            connect_src = "'self' https:"
        else:
            connect_src = "'self' http://localhost:* ws://localhost:* https:"

        # Content Security Policy - prevents XSS attacks
        csp_directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # unsafe-inline needed for styled-components
            "img-src 'self' https: data:",
            f"connect-src {connect_src}",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Enable browser XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Enforce HTTPS in production
        if self.is_production:
            # HSTS header - force HTTPS for 1 year
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Permissions Policy - restrict browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response
