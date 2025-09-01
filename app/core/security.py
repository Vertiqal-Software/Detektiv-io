# app/core/security.py
"""
Password hashing utilities using PBKDF2-HMAC (SHA-256).

Stored format:
    pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

Environment overrides (optional):
    SECURITY_PBKDF2_ITERATIONS   int, default 480000
    SECURITY_SALT_BYTES          int, default 16
    SECURITY_HASH_BYTES          int, default 32

Optional password strength controls (non-breaking; off by default):
    SECURITY_REQUIRE_STRONG      bool, default false (0/1, true/false)
    SECURITY_MIN_LENGTH          int,  default 8
    SECURITY_REQUIRE_CLASSES     bool, default false
        When true, require at least 3 of 4 classes: lower/upper/digit/special

Optional pepper (application-wide secret, OFF by default):
    SECURITY_PASSWORD_PEPPER     str, default '' (empty → no pepper applied)
    SECURITY_PEPPER_REQUIRED     bool, default false
        If true but no pepper is set, hashing/verification will raise ValueError.

Notes on PEPPER:
- A pepper strengthens hashes by mixing in an app-secret with the user password.
- Enabling a pepper later will invalidate verification of hashes created without it.
  Only enable pepper at project start or plan a rehash/rotation strategy.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import string
from typing import Tuple, Dict, Optional


ALGO_NAME = "pbkdf2_sha256"


def _to_int(env_key: str, default: int) -> int:
    val = os.getenv(env_key)
    if not val:
        return default
    try:
        n = int(val)
        return n if n > 0 else default
    except ValueError:
        return default


def _to_bool(env_key: str, default: bool = False) -> bool:
    v = (os.getenv(env_key) or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    if v in {"0", "false", "no", "n"}:
        return False
    return default


DEFAULT_ITERATIONS = _to_int("SECURITY_PBKDF2_ITERATIONS", 480000)
SALT_BYTES = _to_int("SECURITY_SALT_BYTES", 16)
HASH_BYTES = _to_int("SECURITY_HASH_BYTES", 32)

# Optional strength controls (non-breaking; off by default)
REQUIRE_STRONG = _to_bool("SECURITY_REQUIRE_STRONG", False)
MIN_LENGTH = _to_int("SECURITY_MIN_LENGTH", 8)
REQUIRE_CLASSES = _to_bool("SECURITY_REQUIRE_CLASSES", False)

# Optional pepper controls
PEPPER: str = os.getenv("SECURITY_PASSWORD_PEPPER", "") or ""
PEPPER_REQUIRED: bool = _to_bool("SECURITY_PEPPER_REQUIRED", False)


def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def assess_password_strength(password: str) -> Dict[str, bool]:
    """
    Returns a dict indicating presence of character classes and length condition.
    Does not enforce; enforcement is controlled by env flags.
    """
    has_lower = any("a" <= ch <= "z" for ch in password)
    has_upper = any("A" <= ch <= "Z" for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    has_special = any(not ch.isalnum() for ch in password)
    meets_length = len(password) >= MIN_LENGTH
    classes = sum([has_lower, has_upper, has_digit, has_special])
    return {
        "has_lower": has_lower,
        "has_upper": has_upper,
        "has_digit": has_digit,
        "has_special": has_special,
        "meets_length": meets_length,
        "classes_count": classes >= 3,
    }


def _assert_password_strong(password: str) -> None:
    """
    Enforce strength only if REQUIRE_STRONG (env) is enabled.
    By default, we only reject empty/too-short passwords; complexity is optional.
    """
    if not REQUIRE_STRONG:
        # Still protect against trivially short passwords
        if len(password or "") < max(1, MIN_LENGTH):
            raise ValueError(f"Password must be at least {MIN_LENGTH} characters")
        return

    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")

    strength = assess_password_strength(password)
    if not strength["meets_length"]:
        raise ValueError(f"Password must be at least {MIN_LENGTH} characters")
    if REQUIRE_CLASSES and not strength["classes_count"]:
        raise ValueError(
            "Password must include at least 3 of: lowercase, uppercase, digits, special characters"
        )


def _apply_pepper(password: str) -> bytes:
    """
    Return the bytes to use as PBKDF2 input, optionally mixed with a pepper.
    """
    if PEPPER_REQUIRED and not PEPPER:
        raise ValueError("SECURITY_PEPPER_REQUIRED is true but SECURITY_PASSWORD_PEPPER is empty")
    if not isinstance(password, str):
        raise ValueError("Password must be a string")
    if not PEPPER:
        return password.encode("utf-8")
    # Mix in the pepper by simple concatenation; PBKDF2 will KDF this input.
    return (password + PEPPER).encode("utf-8")


def get_password_hash(password: str) -> str:
    """
    Derive a password hash string using PBKDF2-HMAC(SHA-256).
    Raises ValueError for empty or non-string password.

    Non-breaking: if SECURITY_REQUIRE_STRONG=1, enforce strength checks.
    """
    if not isinstance(password, str):
        raise ValueError("Password must be a string")
    if password == "":
        raise ValueError("Password must not be empty")

    # Optional enforcement (env-controlled)
    _assert_password_strong(password)

    iterations = DEFAULT_ITERATIONS
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", _apply_pepper(password), salt, iterations, dklen=HASH_BYTES
    )
    return f"{ALGO_NAME}${iterations}${_b64u_encode(salt)}${_b64u_encode(dk)}"


def _parse_hash(hash_string: str) -> Tuple[int, bytes, bytes]:
    """
    Parse a stored hash string and return (iterations, salt_bytes, hash_bytes).
    Raises ValueError if the format is invalid.
    """
    parts = hash_string.split("$")
    if len(parts) != 4:
        raise ValueError("Invalid hash format")
    algo, iter_s, salt_s, hash_s = parts
    if algo != ALGO_NAME:
        raise ValueError("Unsupported algorithm")
    try:
        iterations = int(iter_s)
    except Exception as e:
        raise ValueError("Invalid iterations") from e
    salt = _b64u_decode(salt_s)
    hashed = _b64u_decode(hash_s)
    if iterations <= 0 or len(salt) == 0 or len(hashed) == 0:
        raise ValueError("Invalid hash components")
    return iterations, salt, hashed


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a password against a stored hash. Returns True/False.
    Any parsing error yields False to avoid leaking details.
    """
    try:
        iterations, salt, expected = _parse_hash(stored_hash)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", _apply_pepper(password), salt, iterations, dklen=len(expected)
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def needs_rehash(stored_hash: str) -> bool:
    """
    Return True if the stored hash should be upgraded (e.g., iterations increased).
    """
    try:
        iterations, _salt, digest = _parse_hash(stored_hash)
        if iterations < DEFAULT_ITERATIONS:
            return True
        return len(digest) != HASH_BYTES
    except Exception:
        # If unreadable, treat as needing rehash
        return True


def rehash_if_needed(password: str, stored_hash: str) -> str | None:
    """
    Convenience: if needs_rehash(stored_hash) and the password verifies,
    return a new hash; otherwise return None. Caller should persist the new
    hash if a value is returned.
    """
    try:
        if not needs_rehash(stored_hash):
            return None
        if not verify_password(password, stored_hash):
            return None
        return get_password_hash(password)
    except Exception:
        # Do not raise from opportunistic upgrade
        return None


# ------------------------- Optional Utilities ------------------------- #

def is_valid_hash(hash_string: str) -> bool:
    """Lightweight format check for a hash string."""
    try:
        _parse_hash(hash_string)
        return True
    except Exception:
        return False


def random_password(
    length: int = 16,
    *,
    require_classes: bool = True,
    alphabet: Optional[str] = None,
) -> str:
    """
    Generate a random password suitable for admin bootstrap or resets.
    Default alphabet mixes ascii letters, digits, and punctuation (excluding ambiguous quotes/space).
    When require_classes=True, ensure at least 3 of 4 classes appear.
    """
    if alphabet is None:
        # Avoid characters that often cause quoting issues in shells
        safe_punct = "!#$%&()*+,-./:;<=>?@[]^_{|}~"
        alphabet = string.ascii_lowercase + string.ascii_uppercase + string.digits + safe_punct

    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(max(8, length)))
        if not require_classes:
            return pwd
        s = assess_password_strength(pwd)
        if s["classes_count"] and s["meets_length"]:
            return pwd


def password_policy_summary() -> str:
    """
    Return a short human-readable summary of the current password policy based on env flags.
    """
    parts = [f"Min length: {MIN_LENGTH}"]
    if REQUIRE_STRONG:
        parts.append("Strong passwords required")
        if REQUIRE_CLASSES:
            parts.append("≥3 character classes")
    else:
        parts.append("Strong enforcement: off")
    if PEPPER:
        parts.append("Pepper: enabled")
    return "; ".join(parts)
