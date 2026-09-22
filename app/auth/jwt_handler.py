import os
import jwt
import uuid
import warnings
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# JWT Secret Key handling with environment-aware security
_jwt_secret = os.getenv("JWT_SECRET_KEY")
if not _jwt_secret:
    if os.getenv("APP_ENV", "development") == "production":
        raise RuntimeError(
            "JWT_SECRET_KEY must be set in production. "
            "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    # Development fallback - warn but allow
    warnings.warn(
        "JWT_SECRET_KEY not set - using insecure default for development only. "
        "DO NOT use this in production!",
        UserWarning
    )
    _jwt_secret = "dev-only-insecure-key-do-not-use-in-production"

SECRET_KEY = _jwt_secret
ALGORITHM = "HS256"

# Security best practices: short-lived access tokens, longer-lived refresh tokens
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a short-lived access token (default 15 minutes).

    Access tokens are used for API requests and should be short-lived
    to minimize security risk if compromised.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Add JWT ID (jti) for blacklist tracking
    jti = str(uuid.uuid4())

    to_encode.update({
        "exp": expire,
        "jti": jti,
        "iat": datetime.utcnow(),
        "type": "access"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a long-lived refresh token (default 7 days).

    Refresh tokens are used to obtain new access tokens without
    requiring the user to log in again.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Add JWT ID (jti) for blacklist tracking
    jti = str(uuid.uuid4())

    to_encode.update({
        "exp": expire,
        "jti": jti,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_token(data: Dict[str, Any], expires_in_days: int = 7) -> str:
    """
    Legacy function for backward compatibility.
    Creates a long-lived token (7 days default).

    NOTE: For new code, use create_access_token() and create_refresh_token() instead.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expires_in_days)

    # Add JWT ID (jti) for blacklist tracking
    jti = str(uuid.uuid4())

    to_encode.update({
        "exp": expire,
        "jti": jti,
        "iat": datetime.utcnow()
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, check_blacklist: bool = True) -> Optional[Dict[str, Any]]:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token string
        check_blacklist: Whether to check if token is blacklisted (default True)

    Returns:
        Decoded payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if token is blacklisted
        if check_blacklist:
            from app.auth.token_blacklist import get_token_blacklist
            blacklist = get_token_blacklist()

            jti = payload.get("jti")
            if jti and blacklist.is_blacklisted(jti):
                return None

            # Check if user has been globally blacklisted
            github_id = payload.get("github_id")
            if github_id and blacklist.is_user_blacklisted(str(github_id)):
                return None

        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None