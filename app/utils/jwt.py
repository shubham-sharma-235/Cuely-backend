import hashlib
import secrets
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from jose import jwt, JWTError

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM  = os.getenv("ALGORITHM", "HS256")

# Access token: short — forces frequent re-validation against DB
ACCESS_TOKEN_EXPIRE_MINUTES  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES",  "15"))

# Refresh token: long — user stays logged in across days/weeks
REFRESH_TOKEN_EXPIRE_DAYS    = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",    "30"))


# ── Access token ──────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "type":    "access",
        "exp":     datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate an access token. Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")


# ── Refresh token ─────────────────────────────────────────────────────────

def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """
    Returns (raw_token, token_hash, expires_at).
    Store the hash in DB; send raw_token to client.
    """
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "user_id": user_id,
        "type":    "refresh",
        "exp":     expires_at,
        # Add a random nonce so each refresh token is unique even for the same user
        "jti":     secrets.token_hex(16),
    }
    raw   = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed, expires_at


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token. Raises ValueError on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid refresh token: {e}")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Legacy alias (keeps existing callers working during migration) ─────────
def create_token(data: dict) -> str:
    """Backward-compat wrapper — new code should use create_access_token."""
    user_id = data.get("user_id")
    if user_id is None:
        raise ValueError("data must contain user_id")
    return create_access_token(int(user_id))