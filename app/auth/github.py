import os
import httpx
import ssl
import secrets
import logging
from typing import Optional, Dict, Any, Union
from redis import Redis

logger = logging.getLogger(__name__)

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# SSL Configuration from environment
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() == "true"
SSL_CA_BUNDLE = os.getenv("SSL_CA_BUNDLE", None)
TLS_MIN_VERSION = float(os.getenv("TLS_MIN_VERSION", "1.2"))


def create_ssl_context(verify: bool = True) -> Union[bool, ssl.SSLContext]:
    """Create robust SSL context that works across OpenSSL versions.

    Args:
        verify: Whether to verify SSL certificates

    Returns:
        SSL context object, True (default verification), or False (no verification)
    """
    # Skip SSL verification if disabled globally or locally
    if not verify or not SSL_VERIFY:
        logger.warning("SSL verification disabled - use only in development!")
        return False

    try:
        # Create default SSL context
        ctx = ssl.create_default_context()

        # Set TLS version constraints for compatibility
        if TLS_MIN_VERSION >= 1.3:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        elif TLS_MIN_VERSION >= 1.2:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        else:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # Default to TLS 1.2

        # Disable old insecure protocols
        ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

        # Load CA certificates
        if SSL_CA_BUNDLE and os.path.exists(SSL_CA_BUNDLE):
            # Use custom CA bundle if specified (for corporate environments)
            ctx.load_verify_locations(SSL_CA_BUNDLE)
            logger.info(f"Loaded custom CA bundle from {SSL_CA_BUNDLE}")
        else:
            # Load certifi CA bundle for consistent certificate validation
            try:
                import certifi
                ctx.load_verify_locations(certifi.where())
                logger.debug("Loaded certifi CA bundle")
            except ImportError:
                logger.warning("certifi not available, using system certificates")

        return ctx
    except Exception as e:
        logger.warning(f"Failed to create custom SSL context: {e}, falling back to default")
        return True  # httpx uses default system verification

async def get_github_auth_url():
    """Generate GitHub OAuth URL and state token"""
    state = secrets.token_urlsafe(32)
    
    # Store state in Redis (expires in 10 minutes)
    r = Redis.from_url(REDIS_URL)
    r.setex(f"oauth_state:{state}", 600, "valid")
    
    auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=user:email%20read:user"
        f"&state={state}"
    )
    return auth_url, state

async def exchange_code_for_token(code: str, state: str) -> Optional[str]:
    """Exchange GitHub code for access token"""
    # Verify state token
    r = Redis.from_url(REDIS_URL)
    if not r.get(f"oauth_state:{state}"):
        return None  # Invalid state

    r.delete(f"oauth_state:{state}")  # One-time use

    # Exchange code for token with robust SSL handling
    is_dev = os.getenv("APP_ENV", "development") == "development"
    ssl_context = create_ssl_context(verify=not is_dev)

    # Increased timeout for slow networks
    async with httpx.AsyncClient(verify=ssl_context, timeout=60.0) as client:
        try:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GITHUB_REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()  # Explicit status check
        except httpx.ConnectError as e:
            logger.error(
                f"Failed to connect to GitHub OAuth: {e.__class__.__name__}: {str(e)}. "
                f"Verify Docker networking and TLS configuration. "
                f"APP_ENV={os.getenv('APP_ENV', 'not set')}, SSL context type: {type(ssl_context).__name__}"
            )
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub OAuth API error: {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during GitHub OAuth token exchange: {e.__class__.__name__}: {str(e)}")
            return None

    data = response.json()
    return data.get("access_token")

async def get_github_user(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch user info from GitHub"""
    # Use robust SSL handling
    is_dev = os.getenv("APP_ENV", "development") == "development"
    ssl_context = create_ssl_context(verify=not is_dev)

    # Increased timeout for slow networks
    async with httpx.AsyncClient(verify=ssl_context, timeout=60.0) as client:
        try:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()  # Explicit status check
        except httpx.ConnectError as e:
            logger.error(
                f"Failed to connect to GitHub API: {e.__class__.__name__}: {str(e)}. "
                f"Verify Docker networking and TLS configuration. "
                f"APP_ENV={os.getenv('APP_ENV', 'not set')}, SSL context type: {type(ssl_context).__name__}"
            )
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub API error: {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching GitHub user info: {e.__class__.__name__}: {str(e)}")
            return None

    return response.json()