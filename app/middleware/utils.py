"""
Middleware utilities for safe response handling.
"""
from starlette.responses import StreamingResponse


def is_streaming_response(response) -> bool:
    """
    Check if a response is a StreamingResponse.

    Args:
        response: The response object to check

    Returns:
        True if response is a StreamingResponse instance
    """
    return isinstance(response, StreamingResponse)


def should_skip_response_modification(response) -> bool:
    """
    Determine if response should skip cookie/header modifications.

    Checks for:
    - StreamingResponse (streaming data, can't modify safely)
    - 3xx redirects (Firefox compatibility issue)

    Args:
        response: The response object to check

    Returns:
        True if response modifications should be skipped
    """
    # Check for streaming response
    if is_streaming_response(response):
        return True

    # Check for redirect status (3xx)
    # Access status_code safely with getattr in case of unusual response types
    status_code = getattr(response, 'status_code', 200)
    if 300 <= status_code < 400:
        return True

    return False
