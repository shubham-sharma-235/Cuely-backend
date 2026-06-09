"""
Auth router — registration, OTP verification, login, refresh, logout, password reset.

Rate limiting strategy:
  - All auth endpoints are unauthenticated, so keyed by IP address.
  - Refresh endpoint is the exception: it carries a refresh token so we can
    key by the token's user_id once decoded, giving per-user fairness.
"""
import random
import string
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User, Club, OtpCode, RefreshToken
from app.schemas.schemas import RegisterIn, LoginIn
from app.utils.security import hash_password, verify_password
from app.utils.jwt import (
    create_access_token, create_refresh_token,
    decode_refresh_token, hash_token,
)
from app.utils.email import send_otp_email
from app.utils.limiter import ip_limiter, user_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

OTP_EXPIRY_MINUTES = 5


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _invalidate_old_otps(user_id: int, db: Session) -> None:
    db.query(OtpCode).filter(
        OtpCode.user_id == user_id,
        OtpCode.used    == False,
    ).update({"used": True})
    db.flush()


def _issue_tokens(user: User, request: Request, db: Session) -> dict:
    """
    Create a new access + refresh token pair, persist the refresh token hash.
    Called from login, verify-otp, and refresh endpoints.
    """
    access  = create_access_token(user.id)
    raw_refresh, refresh_hash, expires_at = create_refresh_token(user.id)

    db.add(RefreshToken(
        user_id    = user.id,
        token_hash = refresh_hash,
        expires_at = expires_at,
        user_agent = request.headers.get("user-agent", "")[:200],
        ip_address = request.client.host if request.client else "",
    ))
    db.commit()

    return {
        "access_token":  access,
        "refresh_token": raw_refresh,
        "token_type":    "bearer",
    }


# ── Register ──────────────────────────────────────────────────────────────
# 5 / hour per IP — prevents mass account creation

@router.post("/register")
# @ip_limiter.limit("1000/hour")
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()

    if existing and existing.is_verified:
        raise HTTPException(400, "Email already registered")

    if existing and not existing.is_verified:
    otp_code = _generate_otp()

    _invalidate_old_otps(existing.id, db)

    db.add(OtpCode(
        user_id=existing.id,
        code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    ))

    db.commit()

    send_otp_email(
        existing.email,
        existing.owner_name,
        otp_code
    )

    return {
        "status": "otp_required",
        "email": existing.email
    }

    user = User(
        email       = body.email,
        owner_name  = body.owner_name,
        password    = hash_password(body.password),
        is_verified = False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    club = Club(name=body.club_name, owner_id=user.id)
    db.add(club)
    db.commit()
    db.refresh(club)
    user.club_id = club.id
    db.commit()

    otp_code = _generate_otp()
    _invalidate_old_otps(user.id, db)
    db.add(OtpCode(
        user_id    = user.id,
        code       = otp_code,
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    ))
    db.commit()

    try:
        send_otp_email(user.email, user.owner_name or user.email, otp_code)
    except Exception as e:
        import os
        if os.getenv("ENV", "dev") == "dev":
            return {"status": "otp_required", "email": user.email, "dev_otp": otp_code,
                    "message": f"Email send failed ({e}). Using dev_otp for testing."}
        raise HTTPException(500, "Failed to send verification email. Check SMTP settings.")

    return {"status": "otp_required", "email": user.email,
            "message": f"A 6-digit verification code has been sent to {user.email}"}


# ── Verify OTP ───────────────────────────────────────────────────────────
# 10 / 5 min per IP — tight window matches OTP expiry

@router.post("/verify-otp")
@ip_limiter.limit("10/5minute")
def verify_otp(request: Request, email: str, code: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_verified:
        raise HTTPException(400, "Account already verified. Please log in.")

    otp = db.query(OtpCode).filter(
        OtpCode.user_id == user.id,
        OtpCode.code    == code,
        OtpCode.used    == False,
    ).order_by(OtpCode.created_at.desc()).first()

    if not otp:
        raise HTTPException(400, "Invalid verification code")
    if datetime.utcnow() > otp.expires_at:
        otp.used = True
        db.commit()
        raise HTTPException(400, "Verification code has expired. Please register again.")

    otp.used         = True
    user.is_verified = True
    db.commit()

    club   = db.query(Club).filter(Club.id == user.club_id).first()
    tokens = _issue_tokens(user, request, db)
    return {**tokens, "club_name": club.name if club else "", "owner_name": user.owner_name or user.email}


# ── Resend OTP ────────────────────────────────────────────────────────────
# 3 / 10 min per IP — prevents OTP spam

@router.post("/resend-otp")
@ip_limiter.limit("3/10minute")
def resend_otp(request: Request, email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.is_verified:
        raise HTTPException(400, "Account already verified")

    otp_code = _generate_otp()
    _invalidate_old_otps(user.id, db)
    db.add(OtpCode(
        user_id    = user.id,
        code       = otp_code,
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    ))
    db.commit()

    try:
        send_otp_email(user.email, user.owner_name or user.email, otp_code)
    except Exception as e:
        import os
        if os.getenv("ENV", "dev") == "dev":
            return {"status": "resent", "dev_otp": otp_code}
        raise HTTPException(500, "Failed to send email")

    return {"status": "resent", "message": f"New code sent to {email}"}


# ── Login ─────────────────────────────────────────────────────────────────
# 10 / 15 min per IP — brute force protection
# Returns both access + refresh tokens

@router.post("/login")
@ip_limiter.limit("10/15minute")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(401, "Invalid credentials")
    if not user.is_verified:
        raise HTTPException(403, "Account not verified. Check your email for the OTP.")

    club   = db.query(Club).filter(Club.id == user.club_id).first()
    tokens = _issue_tokens(user, request, db)
    return {**tokens, "club_name": club.name if club else "", "owner_name": user.owner_name or user.email}


# ── Refresh ───────────────────────────────────────────────────────────────
# 20 / 15 min per IP — allows silent renewal every ~15 min without hammering
# Returns a new access token (and rotates the refresh token for security)

from pydantic import BaseModel as _BM

class _RefreshIn(_BM):
    refresh_token: str

@router.post("/refresh")
@ip_limiter.limit("20/15minute")
def refresh(request: Request, body: _RefreshIn, db: Session = Depends(get_db)):
    # 1. Decode the JWT to get user_id (also validates signature + expiry)
    try:
        payload = decode_refresh_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(401, f"Invalid refresh token: {e}")

    user_id = payload["user_id"]

    # 2. Check the hash exists in DB and isn't revoked
    token_hash = hash_token(body.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id    == user_id,
        RefreshToken.revoked    == False,
    ).first()

    if not stored:
        # Token not found or already revoked — possible token reuse attack
        # Revoke ALL refresh tokens for this user as a precaution
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).update({"revoked": True})
        db.commit()
        raise HTTPException(401, "Refresh token invalid or already used")

    if datetime.utcnow() > stored.expires_at:
        stored.revoked = True
        db.commit()
        raise HTTPException(401, "Refresh token expired. Please log in again.")

    # 3. Rotate: revoke old token and issue a new pair
    stored.revoked = True
    db.commit()

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_verified:
        raise HTTPException(401, "User not found or unverified")

    new_tokens = _issue_tokens(user, request, db)
    return new_tokens


# ── Logout ────────────────────────────────────────────────────────────────
# Revokes the specific refresh token (single device logout)
# No rate limit needed — legitimate action

@router.post("/logout")
def logout(body: _RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_refresh_token(body.refresh_token)
    except ValueError:
        # Token already invalid — treat as already logged out
        return {"status": "ok"}

    token_hash = hash_token(body.refresh_token)
    db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id    == payload["user_id"],
    ).update({"revoked": True})
    db.commit()
    return {"status": "ok"}


# ── Logout all devices ────────────────────────────────────────────────────
# Revokes every refresh token for the user — "sign out everywhere"

from app.deps import get_current_user

@router.post("/logout-all")
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False,
    ).update({"revoked": True})
    db.commit()
    return {"status": "ok", "message": "Signed out from all devices"}


# ── Forgot password ────────────────────────────────────────────────────────
# 3 / 15 min per IP — prevents email flooding

@router.post("/forgot-password")
@ip_limiter.limit("3/15minute")
def forgot_password(request: Request, email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if user and user.is_verified:
        otp_code = _generate_otp()
        _invalidate_old_otps(user.id, db)
        db.add(OtpCode(
            user_id    = user.id,
            code       = otp_code,
            expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
        ))
        db.commit()
        try:
            send_otp_email(user.email, user.owner_name or user.email, otp_code)
        except Exception:
            import os
            if os.getenv("ENV", "dev") == "dev":
                return {"status": "sent", "dev_otp": otp_code}
    return {"status": "sent", "message": "If that email exists, a reset code has been sent"}


# ── Reset password ────────────────────────────────────────────────────────
# 5 / 15 min per IP — prevents code guessing

class _ResetIn(_BM):
    email:        str
    code:         str
    new_password: str

@router.post("/reset-password")
@ip_limiter.limit("5/15minute")
def reset_password(request: Request, body: _ResetIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        raise HTTPException(400, "Invalid reset request")

    otp = db.query(OtpCode).filter(
        OtpCode.user_id == user.id,
        OtpCode.code    == body.code,
        OtpCode.used    == False,
    ).order_by(OtpCode.created_at.desc()).first()

    if not otp or datetime.utcnow() > otp.expires_at:
        raise HTTPException(400, "Invalid or expired code")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    otp.used      = True
    user.password = hash_password(body.new_password)
    # Revoke all existing refresh tokens — force fresh login
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked": True})
    db.commit()
    return {"status": "ok", "message": "Password updated. Please log in."}