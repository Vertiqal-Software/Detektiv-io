# app/core/security.py
from __future__ import annotations

"""
Password hashing & verification (PBKDF2-HMAC-SHA256).

Design goals
------------
- Safe by default: PBKDF2-HMAC-SHA256 with env-tunable iterations.
- Stable format (new hashes):
    "pbkdf2$sha256$<iter>$<salt_b64url>$<dk_b64url>"
- Back-compat (verification only):
    - "pbkdf2_sha256$<iter>$<salt_b64url>$<dk_b64url>"  (older variant)
    - "$2a$.. / $2b$.. / $2y$.." (bcrypt; if 'bcrypt' package present and allowed)
    - "sha256$<hexdigest>" (very old; verify allowed, never emitted)
- Robust verify: constant-time compare, tolerant base64 decoding, strict parsing.
- Upgrade path: `needs_rehash()` tells you when to re-hash to the new format.
- Optional pepper support via SECURITY_PEPPER (server-side secret, never stored).

Env knobs (optional)
--------------------
- SECURITY_PBKDF2_ITERATIONS  (default 100000, clamped [100000..2000000])
- SECURITY_SALT_BYTES         (default 16,     clamped [8..64])
- SECURITY_HASH_BYTES         (default 32,     clamped [16..64])
- SECURITY_PEPPER             (default "", optional server-side secret)
- SECURITY_ACCEPT_BCRYPT      (default true/1; verify bcrypt if library installed)
- SECURITY_LOG_LEVEL          (default INFO; affects this module's logger)

Convenience helpers
-------------------
- hash_password(plain) -> str                    # emits pbkdf2$sha256$...
- verify_password(plain, hashed) -> bool         # accepts all known formats
- needs_rehash(hashed) -> bool                   # suggests upgrade if legacy/weaker
- verify_and_upgrade(plain, hashed) -> (ok, new_hash|None)
- detect_hash_scheme(hashed) -> 'pbkdf2'|'pbkdf2_sha256'|'bcrypt'|'sha256'|'unknown'
- verify_password_any(plain, hashed) -> bool
- migrate_if_legacy(plain, hashed) -> (ok, new_hash|None)
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Final, Tuple, Optional

# -----------------------------------------------------------------------------
# Module logger (safe defaults)
# -----------------------------------------------------------------------------
_log = logging.getLogger("security")
_level = os.getenv("SECURITY_LOG_LEVEL", "INFO").upper()
try:
    _log.setLevel(_level)
except Exception:
    _log.setLevel("INFO")

# -----------------------------------------------------------------------------
# Algorithm constants
# -----------------------------------------------------------------------------

_ALG: Final[str] = "pbkdf2"
_HASH: Final[str] = "sha256"


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


_ITERATIONS_DEFAULT: Final[int] = 100_000
_ITERATIONS: Final[int] = _clamp(
    int(os.getenv("SECURITY_PBKDF2_ITERATIONS", str(_ITERATIONS_DEFAULT))),
    100_000,
    2_000_000,
)

_SALT_LEN_DEFAULT: Final[int] = 16
_SALT_LEN: Final[int] = _clamp(
    int(os.getenv("SECURITY_SALT_BYTES", str(_SALT_LEN_DEFAULT))),
    8,
    64,
)

_DK_LEN_DEFAULT: Final[int] = 32
_DK_LEN: Final[int] = _clamp(
    int(os.getenv("SECURITY_HASH_BYTES", str(_DK_LEN_DEFAULT))),
    16,
    64,
)

# Optional server-side pepper (never stored; mixed into KDF input)
_PEPPER: Final[str] = os.getenv("SECURITY_PEPPER", "")

# Legacy bcrypt acceptance (optional)
_ACCEPT_BCRYPT: Final[bool] = os.getenv(
    "SECURITY_ACCEPT_BCRYPT", "1"
).strip().lower() in {"1", "true", "yes", "on", "y"}

# Attempt to import bcrypt (optional)
try:
    import bcrypt as _bcrypt  # type: ignore

    _HAVE_BCRYPT = True
except Exception:
    _bcrypt = None  # type: ignore
    _HAVE_BCRYPT = False
    if _ACCEPT_BCRYPT:
        _log.debug("bcrypt module not available; legacy bcrypt verification disabled")


# -----------------------------------------------------------------------------
# Base64 URL-safe helpers (tolerant decoding)
# -----------------------------------------------------------------------------


def _b64u_encode(data: bytes) -> str:
    """URL-safe base64 without padding for compactness."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").encode("ascii").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    """
    URL-safe base64 decode, tolerant of missing padding and already-padded strings.
    """
    if not isinstance(s, str):
        raise TypeError("base64 value must be a string")
    s = s.strip()
    # Try direct decode first
    try:
        return base64.urlsafe_b64decode(s.encode("ascii"))
    except Exception:
        # Add required padding and retry
        pad_len = (-len(s)) % 4
        return base64.urlsafe_b64decode((s + ("=" * pad_len)).encode("ascii"))


# -----------------------------------------------------------------------------
# Core PBKDF2 API
# -----------------------------------------------------------------------------


def _pbkdf2(password: str, salt: bytes, iterations: int, dklen: int) -> bytes:
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    # Mix optional pepper to the password material (server-side only)
    material = (password + _PEPPER) if _PEPPER else password
    return hashlib.pbkdf2_hmac(
        _HASH, material.encode("utf-8"), salt, iterations, dklen=dklen
    )


def _format_hash(iterations: int, salt: bytes, dk: bytes) -> str:
    # New canonical format you use elsewhere in the codebase
    return f"{_ALG}${_HASH}${iterations}${_b64u_encode(salt)}${_b64u_encode(dk)}"


def _parse_hash(stored: str) -> Tuple[str, str, int, bytes, bytes]:
    """
    Parse a stored hash string.
    Accepts the *new* format:
        pbkdf2$sha256$<iter>$<salt_b64url>$<dk_b64url>
    Returns: (alg, hash_name, iterations, salt_bytes, dk_bytes)
    Raises: ValueError on malformed input.
    """
    if not isinstance(stored, str) or "$" not in stored:
        raise ValueError("malformed hash")
    parts = stored.split("$")
    if len(parts) != 5:
        raise ValueError("malformed hash")
    alg, hash_name, iter_s, salt_b64, dk_b64 = parts
    try:
        iterations = int(iter_s)
        if iterations <= 0:
            raise ValueError("iterations must be positive")
    except Exception as e:
        raise ValueError("invalid iterations") from e
    try:
        salt = _b64u_decode(salt_b64)
        dk = _b64u_decode(dk_b64)
    except Exception as e:
        raise ValueError("invalid base64") from e
    return alg, hash_name, iterations, salt, dk


def _parse_old_pbkdf2_sha256(stored: str) -> Optional[Tuple[int, bytes, bytes]]:
    """
    Parse the *older* variant:
        pbkdf2_sha256$<iter>$<salt_b64url>$<dk_b64url>
    Returns: (iterations, salt_bytes, dk_bytes) or None if not matching.
    """
    try:
        scheme, rounds_s, salt_b64, dk_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return None
        rounds = int(rounds_s)
        if rounds <= 0:
            return None
        salt = _b64u_decode(salt_b64)
        dk = _b64u_decode(dk_b64)
        return rounds, salt, dk
    except Exception:
        return None


def _parse_sha256_legacy(stored: str) -> Optional[str]:
    """
    Parse *very old* insecure format:
        sha256$<hexdigest>
    Returns the hex digest or None if not matching.
    """
    if not isinstance(stored, str) or not stored.startswith("sha256$"):
        return None
    try:
        _, hex_digest = stored.split("$", 1)
        if not hex_digest or any(
            ch for ch in hex_digest if ch not in "0123456789abcdef"
        ):
            # tolerate uppercase too
            if not all(ch in "0123456789abcdefABCDEF" for ch in hex_digest):
                return None
        return hex_digest
    except ValueError:
        return None


def generate_salt(length: Optional[int] = None) -> bytes:
    """
    Generate a cryptographically strong random salt.
    """
    ln = _clamp(int(length or _SALT_LEN), 8, 64)
    return os.urandom(ln)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256 with env-tunable params.
    Emits the *new* canonical format:
        "pbkdf2$sha256$<iter>$<salt_b64url>$<dk_b64url>"
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    salt = generate_salt(_SALT_LEN)
    dk = _pbkdf2(password, salt=salt, iterations=_ITERATIONS, dklen=_DK_LEN)
    return _format_hash(_ITERATIONS, salt, dk)


# Back-compat alias (previous name used in some modules/tests)
def get_password_hash(password: str) -> str:  # pragma: no cover - simple alias
    return hash_password(password)


def _is_bcrypt_hash(h: str) -> bool:
    """
    Recognize bcrypt hash prefixes used in the wild.
    """
    if not isinstance(h, str) or not h.startswith("$"):
        return False
    return h.startswith("$2a$") or h.startswith("$2b$") or h.startswith("$2y$")


def _verify_bcrypt(plain_password: str, hashed: str) -> bool:
    """
    Verify using the bcrypt library if available.
    Returns False if bcrypt is not available or verification fails.
    """
    if not _HAVE_BCRYPT or not _ACCEPT_BCRYPT:
        return False
    try:
        # bcrypt expects bytes
        return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))  # type: ignore[attr-defined]
    except Exception:
        return False


def verify_password(plain_password: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored hash string.

    Accepted formats:
      - pbkdf2$sha256$<iter>$<salt>$<dk>     (current; preferred)
      - pbkdf2_sha256$<iter>$<salt>$<dk>     (older variant)
      - $2a$/$2b$/$2y$...                    (bcrypt; optional if package installed)
      - sha256$<hexdigest>                   (very old/insecure; verify-only)
    """
    if not isinstance(plain_password, str) or not isinstance(hashed, str) or not hashed:
        return False

    # 1) Preferred modern format
    if hashed.startswith("pbkdf2$sha256$"):
        try:
            alg, hash_name, iterations, salt, expected = _parse_hash(hashed)
            if alg != _ALG or hash_name != _HASH:
                return False
            computed = _pbkdf2(
                plain_password, salt=salt, iterations=iterations, dklen=len(expected)
            )
            return hmac.compare_digest(computed, expected)
        except Exception:
            return False

    # 2) Older PBKDF2 variant: pbkdf2_sha256$<...>
    parsed_old = _parse_old_pbkdf2_sha256(hashed)
    if parsed_old is not None:
        rounds, salt, expected = parsed_old
        try:
            computed = _pbkdf2(
                plain_password, salt=salt, iterations=rounds, dklen=len(expected)
            )
            return hmac.compare_digest(computed, expected)
        except Exception:
            return False

    # 3) bcrypt (optional)
    if _is_bcrypt_hash(hashed):
        ok = _verify_bcrypt(plain_password, hashed)
        if not ok:
            _log.debug(
                "bcrypt hash detected but verification failed or bcrypt unavailable"
            )
        return ok

    # 4) Very old SHA-256 hexdigest (verify-only)
    hex_digest = _parse_sha256_legacy(hashed)
    if hex_digest is not None:
        try:
            d = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            # Compare entire stored string in constant time
            return hmac.compare_digest(
                ("sha256$" + d).encode("utf-8"), hashed.encode("utf-8")
            )
        except Exception:
            return False

    # Unknown format → False (keeps strictness)
    return False


def needs_rehash(hashed: str) -> bool:
    """
    Decide whether the stored hash should be upgraded (e.g., higher iterations or format).
    - True for any non-pbkdf2$sha256$ format (bcrypt, sha256 legacy, pbkdf2_sha256)
    - True if pbkdf2$sha256$ but iterations < current or dk length < policy
    """
    try:
        if not (isinstance(hashed, str)):
            return True
        if hashed.startswith("pbkdf2$sha256$"):
            alg, hash_name, iterations, _salt, dk = _parse_hash(hashed)
            if alg != _ALG or hash_name != _HASH:
                return True
            if iterations < _ITERATIONS:
                return True
            if len(dk) < _DK_LEN:
                return True
            return False
        # Everything else is legacy and should be upgraded
        return True
    except Exception:
        # Unknown/malformed hashes should be considered for rehash on next successful login.
        return True


def verify_and_upgrade(plain_password: str, hashed: str) -> Tuple[bool, Optional[str]]:
    """
    Verify the password. If it matches and policy has strengthened (or format is legacy),
    return a new pbkdf2$sha256$ hash string to store. Otherwise, return (True, None).

    Returns:
        (ok, new_hash_or_none)
    """
    ok = verify_password(plain_password, hashed)
    if not ok:
        return False, None
    try:
        if needs_rehash(hashed):
            return True, hash_password(plain_password)
        return True, None
    except Exception:
        # If rehashing fails, still treat the verification as ok.
        return True, None


# -----------------------------------------------------------------------------
# New helpers (add-only) for smoother migrations
# -----------------------------------------------------------------------------


def detect_hash_scheme(hashed: str) -> str:
    """
    Best-effort scheme detector for stored password hashes.
    Returns one of:
        'pbkdf2' | 'pbkdf2_sha256' | 'bcrypt' | 'sha256' | 'unknown'
    """
    if isinstance(hashed, str):
        if hashed.startswith("pbkdf2$sha256$"):
            return "pbkdf2"
        if hashed.startswith("pbkdf2_sha256$"):
            return "pbkdf2_sha256"
        if _is_bcrypt_hash(hashed):
            return "bcrypt"
        if _parse_sha256_legacy(hashed) is not None:
            return "sha256"
    return "unknown"


def verify_password_any(plain_password: str, hashed: str) -> bool:
    """
    Verify against all supported formats; returns True on success.
    Thin wrapper around verify_password() for clarity.
    """
    return verify_password(plain_password, hashed)


def migrate_if_legacy(plain_password: str, hashed: str) -> Tuple[bool, Optional[str]]:
    """
    Verify password against known formats. If the stored hash is legacy
    (bcrypt, sha256, or pbkdf2_sha256) and verifies successfully, return a freshly
    minted pbkdf2$sha256$ hash to store. If it's already pbkdf2$sha256$ and the
    policy changed, return an upgraded pbkdf2$sha256$ hash. Otherwise, (ok, None).
    """
    scheme = detect_hash_scheme(hashed)
    if scheme == "pbkdf2":
        return verify_and_upgrade(plain_password, hashed)
    elif scheme in {"bcrypt", "sha256", "pbkdf2_sha256"}:
        ok = verify_password(plain_password, hashed)
        if not ok:
            return False, None
        # Promote to modern pbkdf2$sha256$
        try:
            return True, hash_password(plain_password)
        except Exception:
            # If promotion fails, still accept login; store upgrade later.
            return True, None
    else:
        # Unknown scheme
        return False, None


__all__ = [
    "hash_password",
    "get_password_hash",  # back-compat alias
    "verify_password",
    "needs_rehash",
    "verify_and_upgrade",
    "generate_salt",
    # helpers
    "detect_hash_scheme",
    "verify_password_any",
    "migrate_if_legacy",
]
