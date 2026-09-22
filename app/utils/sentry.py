import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import sentry_sdk, but make it optional
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    logger.warning("sentry_sdk not installed. Sentry error tracking will be disabled.")

SENTRY_DSN = os.getenv("SENTRY_DSN")
ENVIRONMENT = os.getenv("APP_ENV", "development")

def init_sentry():
    """Initialize Sentry SDK for error tracking and performance monitoring"""
    if not SENTRY_AVAILABLE:
        logger.info("Sentry SDK not available. Error tracking disabled.")
        return
    
    if not SENTRY_DSN:
        if ENVIRONMENT != "production":
            logger.info("Sentry DSN not provided. Backend error tracking is disabled.")
        return
    
    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            
            # Performance Monitoring
            traces_sample_rate=1.0 if ENVIRONMENT == "development" else 0.1,
            profiles_sample_rate=1.0 if ENVIRONMENT == "development" else 0.1,
            
            # Integrations
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
                RedisIntegration(),
            ],
            
            # Filter out common errors
            ignore_errors=[
                # HTTP exceptions (4xx) - these are expected
                "HTTPException",
                # Keyboard interrupts
                "KeyboardInterrupt",
            ],
            
            # Set release version
            release=os.getenv("APP_VERSION", "1.0.0"),
            
            # Before send hook to filter/modify events
            before_send=before_send_hook,
        )
        logger.info("Sentry backend initialized successfully.")
    except Exception as e:
        logger.warning(f"Failed to initialize Sentry: {e}. Error tracking disabled.")

def before_send_hook(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Filter or modify events before sending to Sentry"""
    if not SENTRY_AVAILABLE:
        return None
    
    # Filter out errors from health checks
    if event.get("request", {}).get("url", "").endswith("/health"):
        return None
    
    # Add custom tags
    event.setdefault("tags", {})
    event["tags"]["service"] = "repolens-api"
    
    return event

def set_user_context(user_id: Optional[str] = None, email: Optional[str] = None, username: Optional[str] = None):
    """Set user context for Sentry"""
    if not SENTRY_AVAILABLE:
        return
    
    if user_id:
        sentry_sdk.set_user({
            "id": str(user_id),
            "email": email,
            "username": username,
        })

def clear_user_context():
    """Clear user context"""
    if not SENTRY_AVAILABLE:
        return
    
    sentry_sdk.set_user(None)

def capture_exception(error: Exception, **kwargs):
    """Capture an exception to Sentry"""
    if not SENTRY_AVAILABLE:
        return
    
    sentry_sdk.capture_exception(error, **kwargs)

def capture_message(message: str, level: str = "info", **kwargs):
    """Capture a message to Sentry"""
    if not SENTRY_AVAILABLE:
        return
    
    sentry_sdk.capture_message(message, level=level, **kwargs)
