from pydantic import BaseModel, EmailStr
from typing import Optional, List


# ── Auth ──────────────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    club_name:  str
    owner_name: str
    email:      str
    password:   str

class LoginIn(BaseModel):
    email:    str
    password: str


# ── Tables ────────────────────────────────────────────────────────────────

class TableIn(BaseModel):
    table_name:     str
    table_number:   int
    price_per_hour: float


# ── Menu ──────────────────────────────────────────────────────────────────

class MenuItemIn(BaseModel):
    name:     str
    price:    float
    category: str = "General"


# ── Sessions ──────────────────────────────────────────────────────────────

class StartSessionIn(BaseModel):
    table_id:       int
    customer_name:  str
    customer_phone: Optional[str] = None

class AddItemIn(BaseModel):
    table_id: int
    item_id:  int
    quantity: int = 1

class EndSessionIn(BaseModel):
    table_id: int

class SnackEdit(BaseModel):
    item_id:  int
    quantity: int   # 0 = remove

class FinaliseIn(BaseModel):
    session_id:      int
    payment_method:  str                        # cash | upi | card | pay_later
    override_amount: Optional[float]  = None
    snack_edits:     Optional[List[SnackEdit]] = None


# ── Bookings ──────────────────────────────────────────────────────────────

class BookingIn(BaseModel):
    table_id:       int
    customer_name:  str
    customer_phone: Optional[str] = None
    booked_date:    str                         # YYYY-MM-DD
    booked_time:    str                         # HH:MM
    duration_hours: float = 1.0
    notes:          Optional[str] = None


# ── Day Close ─────────────────────────────────────────────────────────────

class DayCloseIn(BaseModel):
    close_date: str   # YYYY-MM-DD


# ── Lender payment ───────────────────────────────────────────────────────

class PayLenderIn(BaseModel):
    session_id:     int
    payment_method: str   # cash | upi | card