from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime

from app.db.session import get_db
from app.models.models import User, Table, GameSession, Booking
from app.schemas.schemas import TableIn
from app.deps import get_current_user

router = APIRouter(prefix="/tables", tags=["tables"])


def _nearest_booking(t, db):
    today_bookings = db.query(Booking).filter(
        Booking.table_id    == t.id,
        Booking.booked_date == date.today().isoformat(),
        Booking.status      == "pending",
    ).all()

    now  = datetime.now()
    best = None
    best_delta = float("inf")

    for b in today_bookings:
        try:
            h, m  = map(int, b.booked_time.split(":"))
            bk_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            delta = (bk_dt - now).total_seconds() / 60   # negative = overdue
            if -30 <= delta <= 120 and delta < best_delta:
                best       = b
                best_delta = delta
        except Exception:
            continue
    return best


def _table_out(t, db):
    active_sess = db.query(GameSession).filter(
        GameSession.table_id == t.id, GameSession.status == "active"
    ).first()

    booking = _nearest_booking(t, db)

    return {
        "id":             t.id,
        "table_name":     t.table_name,
        "table_number":   t.table_number,
        "price_per_hour": t.price_per_hour,
        "is_active":      t.is_active,
        "active_session": _sess_mini(active_sess, db) if active_sess else None,
        "booking":        _booking_mini(booking)       if booking      else None,
    }


def _sess_mini(s, db):
    from app.models.models import SessionItem
    items = db.query(SessionItem).filter(SessionItem.session_id == s.id).all()
    return {
        "id":            s.id,
        "customer_name": s.customer_name,
        "customer_phone":s.customer_phone,
        "start_time":    s.start_time.isoformat(),
        "items": [{"item_id": i.item_id, "item_name": i.item_name,
                   "quantity": i.quantity, "price": i.price} for i in items],
    }


def _booking_mini(b):
    return {
        "id":            b.id,
        "customer_name": b.customer_name,
        "customer_phone":b.customer_phone,
        "booked_date":   b.booked_date,
        "booked_time":   b.booked_time,
        "duration_hours":b.duration_hours,
    }


@router.get("")
def list_tables(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tables = db.query(Table).filter(Table.club_id == user.club_id).order_by(Table.table_number).all()
    return [_table_out(t, db) for t in tables]


@router.post("")
def create_table(body: TableIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = Table(
        club_id=user.club_id,
        table_name=body.table_name,
        table_number=body.table_number,
        price_per_hour=body.price_per_hour,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _table_out(t, db)


@router.put("/{table_id}")
def update_table(table_id: int, body: TableIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Table).filter(Table.id == table_id, Table.club_id == user.club_id).first()
    if not t:
        raise HTTPException(404, "Table not found")
    t.table_name     = body.table_name
    t.table_number   = body.table_number
    t.price_per_hour = body.price_per_hour
    db.commit()
    return _table_out(t, db)


@router.delete("/{table_id}")
def delete_table(table_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    active = db.query(GameSession).filter(
        GameSession.table_id == table_id, GameSession.status == "active"
    ).first()
    if active:
        raise HTTPException(400, "End the active session before deleting this table")
    t = db.query(Table).filter(Table.id == table_id, Table.club_id == user.club_id).first()
    if not t:
        raise HTTPException(404, "Table not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.patch("/{table_id}/toggle")
def toggle_table(table_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Table).filter(Table.id == table_id, Table.club_id == user.club_id).first()
    if not t:
        raise HTTPException(404, "Table not found")
    t.is_active = not t.is_active
    db.commit()
    return {"is_active": t.is_active}