# app/core/utils.py
"""
Utility functions for the Detecktiv.io application.

This module provides common utility functions used across the application
including data validation, formatting, and helper functions.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urlparse, urlunparse
import hashlib
import secrets
import string


def generate_request_id() -> str:
    """Generate a unique request ID for tracking."""
    return str(uuid.uuid4())


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.
    
    Args:
        length: Length of the token to generate
        
    Returns:
        Secure random token
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def hash_string(value: str, salt: Optional[str] = None) -> str:
    """
    Hash a string value using SHA-256.
    
    Args:
        value: String to hash
        salt: Optional salt to add
        
    Returns:
        Hexadecimal hash digest
    """
    if salt:
        value = f"{value}{salt}"
    
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def normalize_url(url: str) -> Optional[str]:
    """
    Normalize a URL to a standard format.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL or None if invalid
    """
    if not url or not url.strip():
        return None
    
    url = url.strip()
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    try:
        parsed = urlparse(url)
        
        # Validate that we have a domain
        if not parsed.netloc:
            return None
        
        # Normalize the URL
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
        
        return normalized
        
    except Exception:
        return None


def validate_email(email: str) -> bool:
    """
    Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not email or not email.strip():
        return False
    
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_uk_postcode(postcode: str) -> bool:
    """
    Validate UK postcode format.
    
    Args:
        postcode: UK postcode to validate
        
    Returns:
        True if valid UK postcode format, False otherwise
    """
    if not postcode or not postcode.strip():
        return False
    
    # UK postcode regex pattern
    pattern = r'^[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}$'
    return bool(re.match(pattern, postcode.strip().upper()))


def format_phone_number(phone: str, country_code: str = 'GB') -> Optional[str]:
    """
    Format phone number to international format.
    
    Args:
        phone: Phone number to format
        country_code: Country code (GB, US, etc.)
        
    Returns:
        Formatted phone number or None if invalid
    """
    if not phone or not phone.strip():
        return None
    
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    
    if country_code == 'GB':
        # UK phone number formatting
        if cleaned.startswith('+44'):
            return cleaned
        elif cleaned.startswith('0044'):
            return f'+44{cleaned[4:]}'
        elif cleaned.startswith('44'):
            return f'+{cleaned}'
        elif cleaned.startswith('0'):
            return f'+44{cleaned[1:]}'
        else:
            return f'+44{cleaned}'
    
    # For other countries, just ensure it starts with +
    if not cleaned.startswith('+'):
        cleaned = f'+{cleaned}'
    
    return cleaned if len(cleaned) >= 8 else None


def format_currency(amount: Optional[Union[int, float]], currency: str = 'GBP') -> str:
    """
    Format currency amount for display.
    
    Args:
        amount: Amount to format
        currency: Currency code
        
    Returns:
        Formatted currency string
    """
    if amount is None:
        return 'N/A'
    
    currency_symbols = {
        'GBP': '£',
        'USD': '$',
        'EUR': '€'
    }
    
    symbol = currency_symbols.get(currency, currency)
    
    if amount >= 1_000_000:
        return f'{symbol}{amount/1_000_000:.1f}M'
    elif amount >= 1_000:
        return f'{symbol}{amount/1_000:.1f}K'
    else:
        return f'{symbol}{amount:,.0f}'


def sanitize_string(value: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize string input for database storage.
    
    Args:
        value: String to sanitize
        max_length: Maximum length to truncate to
        
    Returns:
        Sanitized string
    """
    if not value:
        return ''
    
    # Remove control characters and normalize whitespace
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', str(value))
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip()
    
    return sanitized


def extract_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain name or None if invalid
    """
    normalized_url = normalize_url(url)
    if not normalized_url:
        return None
    
    try:
        parsed = urlparse(normalized_url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
        
    except Exception:
        return None


def calculate_age_from_date(date: datetime) -> int:
    """
    Calculate age in years from a date.
    
    Args:
        date: Date to calculate age from
        
    Returns:
        Age in years
    """
    now = datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    
    age = now - date
    return age.days // 365


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split a list into chunks of specified size.
    
    Args:
        lst: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def safe_get_nested_value(data: Dict[str, Any], keys: str, default: Any = None) -> Any:
    """
    Safely get nested value from dictionary using dot notation.
    
    Args:
        data: Dictionary to search
        keys: Dot-separated key path (e.g., 'user.profile.name')
        default: Default value if not found
        
    Returns:
        Value at the nested key or default
    """
    try:
        keys_list = keys.split('.')
        value = data
        
        for key in keys_list:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
        
    except Exception:
        return default


def convert_to_bool(value: Any) -> bool:
    """
    Convert various types to boolean.
    
    Args:
        value: Value to convert
        
    Returns:
        Boolean representation
    """
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1', 'on', 'enabled')
    
    if isinstance(value, (int, float)):
        return value != 0
    
    return bool(value)


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging.
    
    Args:
        data: Data to mask
        mask_char: Character to use for masking
        visible_chars: Number of characters to leave visible at the end
        
    Returns:
        Masked string
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ''
    
    masked_length = len(data) - visible_chars
    return mask_char * masked_length + data[-visible_chars:]


def validate_companies_house_number(number: str) -> bool:
    """
    Validate Companies House number format.
    
    Args:
        number: Companies House number to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not number or not number.strip():
        return False
    
    # Remove spaces and convert to uppercase
    cleaned = number.strip().upper().replace(' ', '')
    
    # UK company numbers are typically 8 digits, sometimes with 2-letter prefix
    patterns = [
        r'^\d{8}$',  # 8 digits
        r'^[A-Z]{2}\d{6}$',  # 2 letters + 6 digits
        r'^\d{6}$',  # 6 digits (older format)
    ]
    
    return any(re.match(pattern, cleaned) for pattern in patterns)


def generate_slug(text: str, max_length: int = 50) -> str:
    """
    Generate a URL-friendly slug from text.
    
    Args:
        text: Text to slugify
        max_length: Maximum length of slug
        
    Returns:
        URL-friendly slug
    """
    if not text:
        return ''
    
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    
    # Truncate to max length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')
    
    return slug


class DataValidator:
    """
    Utility class for data validation with detailed error reporting.
    """
    
    def __init__(self):
        self.errors = []
    
    def add_error(self, field: str, message: str):
        """Add a validation error."""
        self.errors.append({'field': field, 'message': message})
    
    def validate_required(self, field: str, value: Any):
        """Validate that a field has a value."""
        if value is None or (isinstance(value, str) and not value.strip()):
            self.add_error(field, f'{field} is required')
    
    def validate_email_field(self, field: str, value: Optional[str]):
        """Validate email field."""
        if value and not validate_email(value):
            self.add_error(field, f'{field} must be a valid email address')
    
    def validate_url_field(self, field: str, value: Optional[str]):
        """Validate URL field."""
        if value and not normalize_url(value):
            self.add_error(field, f'{field} must be a valid URL')
    
    def validate_postcode_field(self, field: str, value: Optional[str], country: str = 'GB'):
        """Validate postcode field."""
        if value and country == 'GB' and not validate_uk_postcode(value):
            self.add_error(field, f'{field} must be a valid UK postcode')
    
    def validate_range(self, field: str, value: Optional[Union[int, float]], min_val: Optional[Union[int, float]] = None, max_val: Optional[Union[int, float]] = None):
        """Validate numeric range."""
        if value is not None:
            if min_val is not None and value < min_val:
                self.add_error(field, f'{field} must be at least {min_val}')
            if max_val is not None and value > max_val:
                self.add_error(field, f'{field} must be at most {max_val}')
    
    def is_valid(self) -> bool:
        """Check if all validations passed."""
        return len(self.errors) == 0
    
    def get_errors(self) -> List[Dict[str, str]]:
        """Get all validation errors."""
        return self.errors.copy()
    
    def clear_errors(self):
        """Clear all validation errors."""
        self.errors.clear()
