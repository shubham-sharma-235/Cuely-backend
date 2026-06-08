"""
All SQLAlchemy models in one file.
Import from here everywhere — avoids circular import issues.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    ForeignKey, DateTime, Text, UniqueConstraint,
)
from datetime import datetime
from app.db.session import Base


# ── Users ──────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id          = Column(Integer, primary_key=True, index=True)
    owner_name  = Column(String, nullable=True)
    email       = Column(String, unique=True, index=True, nullable=False)
    password    = Column(String, nullable=False)
    club_id     = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)


# OTP Codes
class OtpCode(Base):
    __tablename__ = "otp_codes"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    code       = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Clubs ─────────────────────────────────────────────────────────────────

class Club(Base):
    __tablename__ = "clubs"

    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)


# ── Tables ────────────────────────────────────────────────────────────────

class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("table_number", "club_id", name="uq_table_number_club"),
    )

    id             = Column(Integer, primary_key=True, index=True)
    club_id        = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    table_name     = Column(String, nullable=False)
    table_number   = Column(Integer, nullable=False)
    price_per_hour = Column(Float, nullable=False)
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)


# ── Game Sessions ─────────────────────────────────────────────────────────

class GameSession(Base):
    __tablename__ = "sessions"

    id              = Column(Integer, primary_key=True, index=True)
    club_id         = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    table_id        = Column(Integer, ForeignKey("tables.id"), nullable=False)

    # Customer
    customer_name   = Column(String, nullable=True)
    customer_phone  = Column(String, nullable=True)   # normalised 10-digit

    # Timing
    start_time      = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time        = Column(DateTime, nullable=True)

    # Billing amounts (all stored separately for audit)
    game_amount     = Column(Float, nullable=True)
    snack_amount    = Column(Float, nullable=True)
    override_amount = Column(Float, nullable=True)    # manual override by owner
    total_amount    = Column(Float, nullable=True)

    # status: active | pending | collected | pay_later
    status          = Column(String, default="active", nullable=False)
    payment_method  = Column(String, nullable=True)   # cash | upi | card

    # Legacy compat (kept so old DB rows don't break)
    is_finalized    = Column(Boolean, default=False)

    created_at      = Column(DateTime, default=datetime.utcnow)


# ── Session Items ─────────────────────────────────────────────────────────

class SessionItem(Base):
    __tablename__ = "session_items"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    item_id    = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    item_name  = Column(String, nullable=True)   # snapshot name at time of sale
    quantity   = Column(Integer, default=1, nullable=False)
    price      = Column(Float, nullable=False)   # snapshot price at time of sale


# ── Menu Items ────────────────────────────────────────────────────────────

class MenuItem(Base):
    __tablename__ = "menu_items"

    id       = Column(Integer, primary_key=True, index=True)
    club_id  = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    name     = Column(String, nullable=False)
    price    = Column(Float, nullable=False)
    category = Column(String, nullable=True, default="General")  # e.g. Cold Drinks, Snacks, Hot Drinks


# ── Customers (phone-linked profiles) ────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id         = Column(Integer, primary_key=True, index=True)
    club_id    = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    name       = Column(String, nullable=False)
    phone      = Column(String, nullable=True)   # normalised 10-digit
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Advance Bookings ──────────────────────────────────────────────────────

class Booking(Base):
    __tablename__ = "bookings"

    id             = Column(Integer, primary_key=True, index=True)
    club_id        = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    table_id       = Column(Integer, ForeignKey("tables.id"), nullable=False)
    customer_name  = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    booked_date    = Column(String, nullable=False)    # YYYY-MM-DD
    booked_time    = Column(String, nullable=False)    # HH:MM (24hr)
    duration_hours = Column(Float, default=1.0)
    notes          = Column(String, nullable=True)
    # status: pending | checked_in | cancelled
    status         = Column(String, default="pending", nullable=False)
    session_id     = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


# ── Day Close Summaries ───────────────────────────────────────────────────

class DayClose(Base):
    __tablename__ = "day_closes"

    id             = Column(Integer, primary_key=True, index=True)
    club_id        = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    close_date     = Column(String, nullable=False)   # YYYY-MM-DD
    summary_json   = Column(Text, nullable=False)     # full JSON snapshot
    total_revenue  = Column(Float, default=0)
    cash_revenue   = Column(Float, default=0)
    upi_revenue    = Column(Float, default=0)
    card_revenue   = Column(Float, default=0)
    pending_amount = Column(Float, default=0)
    total_sessions = Column(Integer, default=0)
    created_at     = Column(DateTime, default=datetime.utcnow)



# ── Refresh Tokens ────────────────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, index=True)  # SHA-256 of the raw token
    expires_at = Column(DateTime, nullable=False)
    revoked    = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Track which device/session created this token (useful for "sign out all")
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

# ── Game Types (kept for backward compat) ────────────────────────────────

class GameType(Base):
    __tablename__ = "game_types"

    id      = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"))
    name    = Column(String, nullable=False)