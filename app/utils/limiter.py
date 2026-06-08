"""
Rate limiting using slowapi (wraps limits library).

Install: pip install slowapi

TWO KEYING STRATEGIES
─────────────────────
1. By IP address  — used for unauthenticated routes (register, login, OTP).
   Protects against bots that don't have a valid token.

2. By user ID     — used for authenticated routes.
   Fairer: a shared office NAT (many users, one IP) won't be penalised as a
   group. Each paying club owner gets their own independent bucket.

LIMITS SUMMARY
──────────────
  Unauthenticated (keyed by IP):
    POST /auth/register        5 / hour       mass account creation
    POST /auth/login          10 / 15 min     brute force
    POST /auth/verify-otp     10 / 5 min      OTP guessing
    POST /auth/resend-otp      3 / 10 min     email flooding
    POST /auth/forgot-password 3 / 15 min     email flooding
    POST /auth/reset-password  5 / 15 min     code guessing
    POST /auth/refresh        20 / 15 min     token refresh abuse

  Authenticated (keyed by user ID, falls back to IP):
    Dashboard / tables / menu 120 / minute    generous — supports polling
    Session mutations          60 / minute    start/end/add-item
    Analytics / reporting      30 / minute    heavier DB queries

  Global fallback:            200 / minute    catches anything undecorated
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_user_or_ip(request: Request) -> str:
    """
    Key authenticated requests by user_id extracted from the JWT payload.
    Falls back to IP for unauthenticated requests.
    This prevents a shared NAT from exhausting the quota for all users behind it.
    """
    # deps.py stores the decoded payload on request.state after auth succeeds
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return get_remote_address(request)


# Two limiters — one per keying strategy
ip_limiter   = Limiter(key_func=get_remote_address,  default_limits=["200/minute"])
user_limiter = Limiter(key_func=get_user_or_ip,      default_limits=["200/minute"])

# Convenience alias used by main.py (mounts the middleware once)
limiter = ip_limiter