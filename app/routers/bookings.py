from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime,UTC
from typing import Optional

from app.db.session import get_db
from app.models.models import User, Booking, Table, GameSession
from app.schemas.schemas import BookingIn
from app.deps import get_current_user, normalise_phone

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _booking_out(b: Booking, db: Session) -> dict:
    table = db.query(Table).filter(Table.id == b.table_id).first()
    return {
        "id":             b.id,
        "table_id":       b.table_id,
        "table_name":     table.table_name if table else "?",
        "customer_name":  b.customer_name,
        "customer_phone": b.customer_phone,
        "booked_date":    b.booked_date,
        "booked_time":    b.booked_time,
        "duration_hours": b.duration_hours,
        "notes":          b.notes,
        "status":         b.status,
        "session_id":     b.session_id,
    }


@router.get("")
def list_bookings(
    date_filter: Optional[str] = Query(None),
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    q = db.query(Booking).filter(Booking.club_id == user.club_id)
    if date_filter:
        q = q.filter(Booking.booked_date == date_filter)
    return [_booking_out(b, db) for b in q.order_by(Booking.booked_date, Booking.booked_time).all()]


@router.post("")
def create_booking(body: BookingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Conflict check: same table, same date, same time, still pending
    conflict = db.query(Booking).filter(
        Booking.club_id     == user.club_id,
        Booking.table_id    == body.table_id,
        Booking.booked_date == body.booked_date,
        Booking.booked_time == body.booked_time,
        Booking.status      == "pending",
    ).first()
    if conflict:
        raise HTTPException(400, f"Booking conflict: table already reserved at {body.booked_time}")

    phone = normalise_phone(body.customer_phone) #if body.customer_phone else None
    bk = Booking(
        club_id=user.club_id,
        table_id=body.table_id,
        customer_name=body.customer_name,
        customer_phone=phone,
        booked_date=body.booked_date,
        booked_time=body.booked_time,
        duration_hours=body.duration_hours,
        notes=body.notes,
    )
    db.add(bk)
    db.commit()
    db.refresh(bk)
    return _booking_out(bk, db)


@router.put("/{booking_id}")
def update_booking(booking_id: int, body: BookingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bk = db.query(Booking).filter(Booking.id == booking_id, Booking.club_id == user.club_id).first()
    if not bk:
        raise HTTPException(404, "Booking not found")
    if bk.status != "pending":
        raise HTTPException(400, "Only pending bookings can be edited")
    bk.customer_name  = body.customer_name
    bk.customer_phone = normalise_phone(body.customer_phone) if body.customer_phone else None
    bk.table_id       = body.table_id
    bk.booked_date    = body.booked_date
    bk.booked_time    = body.booked_time
    bk.duration_hours = body.duration_hours
    bk.notes          = body.notes
    db.commit()
    return _booking_out(bk, db)


@router.post("/{booking_id}/checkin")
def checkin_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bk = db.query(Booking).filter(Booking.id == booking_id, Booking.club_id == user.club_id).first()
    if not bk or bk.status != "pending":
        raise HTTPException(404, "Pending booking not found")

    already = db.query(GameSession).filter(
        GameSession.table_id == bk.table_id, GameSession.status == "active"
    ).first()
    if already:
        raise HTTPException(400, "Table already has an active session")

    sess = GameSession(
        club_id=user.club_id,
        table_id=bk.table_id,
        customer_name=bk.customer_name,
        customer_phone=bk.customer_phone,
        start_time=datetime.now(UTC),
        status="active",
    )
    db.add(sess)
    bk.status = "checked_in"
    db.flush()
    bk.session_id = sess.id
    db.commit()
    return {"session_id": sess.id, "message": f"Checked in {bk.customer_name}"}


@router.patch("/{booking_id}/cancel")
def cancel_booking(booking_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bk = db.query(Booking).filter(Booking.id == booking_id, Booking.club_id == user.club_id).first()
    if not bk:
        raise HTTPException(404, "Booking not found")
    bk.status = "cancelled"
    db.commit()
    return {"ok": True}
