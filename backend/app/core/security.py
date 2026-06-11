"""Security utilities: JWT tokens, password hashing, authentication.

Password hashing uses the ``bcrypt`` library directly rather than passlib's
``CryptContext``. passlib 1.7 is incompatible with bcrypt >= 4 (its backend
probe calls ``hashpw`` with an over-72-byte value, which modern bcrypt rejects
with a ``ValueError`` instead of truncating — breaking every hash/verify and
returning HTTP 500 on login). Calling bcrypt directly removes that version
coupling and stays compatible with existing ``$2b$`` hashes.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt only uses the first 72 bytes of the password; modern bcrypt raises if
# given more, so we truncate explicitly (matching passlib's historical behavior).
_BCRYPT_MAX_BYTES = 72

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify and decode a JWT token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _to_bcrypt_bytes(password: str) -> bytes:
    """Encode and truncate a password to bcrypt's 72-byte input limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    """Hash a password for storage using bcrypt."""
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")
