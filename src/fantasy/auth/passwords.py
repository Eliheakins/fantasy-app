"""Password hashing with the standard library's scrypt.

Cost is OWASP's minimum for scrypt (N=2^17, r=8, p=1), about 128 MiB and a third of a second per
hash (OWASP Password Storage Cheat Sheet). That much memory per login would let a burst of requests
exhaust a small server, so at most MAX_CONCURRENT_HASHES run at once. A stored hash carries its own
parameters, so raising the cost later does not lock anyone out.

Stored form: scrypt$N$r$p$salt$hash (salt and hash in base64).
"""

import base64
import binascii
import hashlib
import hmac
import logging
import os
import threading
from functools import lru_cache

log = logging.getLogger(__name__)

COST_N = 2**17
COST_R = 8
COST_P = 1
KEY_BYTES = 32
SALT_BYTES = 16
MAX_MEMORY = 256 * 1024 * 1024
MAX_CONCURRENT_HASHES = 2
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256  # a longer one only costs the server time
# A stored hash is trusted data, but a tampered one must not be able to demand unlimited memory.
LIMIT_N, LIMIT_R, LIMIT_P = 2**20, 16, 4

_slots = threading.BoundedSemaphore(MAX_CONCURRENT_HASHES)


def _scrypt(password: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, maxmem=MAX_MEMORY, dklen=KEY_BYTES)


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    with _slots:
        return _scrypt(password.encode(), salt, n, r, p)


def check_length(password: str) -> str | None:
    """Why this password is not acceptable, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Use at most {MAX_PASSWORD_LENGTH} characters."
    return None


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    key = _derive(password, salt, COST_N, COST_R, COST_P)
    parts = (COST_N, COST_R, COST_P, _b64(salt), _b64(key))
    return "scrypt$" + "$".join(str(part) for part in parts)


def verify_password(password: str, stored: str) -> bool:
    """True only for the right password; a malformed stored value is simply False."""
    try:
        scheme, n_text, r_text, p_text, salt, key = stored.split("$")
        n, r, p = int(n_text), int(r_text), int(p_text)
        if scheme != "scrypt" or not (0 < n <= LIMIT_N and 0 < r <= LIMIT_R and 0 < p <= LIMIT_P):
            return False
        expected = base64.b64decode(key, validate=True)
        actual = _derive(password, base64.b64decode(salt, validate=True), n, r, p)
    except (ValueError, binascii.Error):
        # Unreadable hash, not a wrong password: say so, without the hash or the password.
        log.error("stored password hash is malformed")
        return False
    return hmac.compare_digest(actual, expected)


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """Checked for an unknown email, so a wrong email costs the same time as a wrong password."""
    return hash_password("this password belongs to nobody")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()
