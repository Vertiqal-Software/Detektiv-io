# app/core/utils.py
"""
Core utilities for the application.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional, List, Union
from datetime import datetime, timezone

logger = logging.getLogger("api.utils")


def get_env_bool(name: str, default: bool = False) -> bool:
    """
    Get boolean value from environment variable.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Boolean value
    """
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "y"}


def get_env_list(name: str, separator: str = ",") -> List[str]:
    """
    Get list from comma-separated environment variable.

    Args:
        name: Environment variable name
        separator: Separator character

    Returns:
        List of stripped values
    """
    value = os.getenv(name, "").strip()
    if not value:
        return []
    return [item.strip() for item in value.split(separator) if item.strip()]


def sanitize_dict(
    data: Dict[str, Any], sensitive_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize dictionary by masking sensitive values.

    Args:
        data: Dictionary to sanitize
        sensitive_keys: Keys to mask (default: password, token, etc.)

    Returns:
        Sanitized dictionary
    """
    if sensitive_keys is None:
        sensitive_keys = [
            "password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "authorization",
            "auth",
        ]

    result = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            result[key] = "***" if value else None
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value, sensitive_keys)
        elif isinstance(value, list):
            result[key] = [
                sanitize_dict(item, sensitive_keys) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def format_error_response(
    error_code: int,
    message: str,
    details: Optional[Union[str, List[Any], Dict[str, Any]]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format standardized error response.

    Args:
        error_code: HTTP error code
        message: Error message
        details: Optional error details
        request_id: Optional request ID

    Returns:
        Formatted error dictionary
    """
    response = {"error": {"code": error_code, "message": message}}

    if details is not None:
        response["error"]["details"] = details

    if request_id:
        response["request_id"] = request_id

    return response


def validate_pagination(
    limit: Optional[int] = None, offset: Optional[int] = None, max_limit: int = 1000
) -> Dict[str, int]:
    """
    Validate and normalize pagination parameters.

    Args:
        limit: Items per page
        offset: Items to skip
        max_limit: Maximum allowed limit

    Returns:
        Dictionary with validated limit and offset
    """
    if limit is None:
        limit = 50
    elif limit < 1:
        limit = 1
    elif limit > max_limit:
        limit = max_limit

    if offset is None:
        offset = 0
    elif offset < 0:
        offset = 0

    return {"limit": limit, "offset": offset}
