from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.db.session import get_db
from app.models.models import User, Table, GameSession, SessionItem, MenuItem, Customer
from app.schemas.schemas import StartSessionIn, AddItemIn, EndSessionIn, FinaliseIn
from app.deps import get_current_user, normalise_phone

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _session_out(s: GameSession, db: Session) -> dict:
    items = db.query(SessionItem).filter(SessionItem.session_id == s.id).all()
    return {
        "id":              s.id,
        "table_id":        s.table_id,
        "customer_name":   s.customer_name,
        "customer_phone":  s.customer_phone,
        "start_time":      s.start_time.isoformat() if s.start_time else None,
        "end_time":        s.end_time.isoformat()   if s.end_time   else None,
        "status":          s.status,
        "payment_method":  s.payment_method,
        "game_amount":     s.game_amount,
        "snack_amount":    s.snack_amount,
        "override_amount": s.override_amount,
        "total_amount":    s.total_amount,
        "items": [
            {"id": i.id, "item_id": i.item_id, "item_name": i.item_name,
             "quantity": i.quantity, "price": i.price}
            for i in items
        ],
    }


@router.post("/start")
def start_session(body: StartSessionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = db.query(Table).filter(Table.id == body.table_id, Table.club_id == user.club_id).first()
    if not table:
        raise HTTPException(404, "Table not found")
    if not table.is_active:
        raise HTTPException(400, "Table is inactive")

    already = db.query(GameSession).filter(
        GameSession.table_id == body.table_id, GameSession.status == "active"
    ).first()
    if already:
        raise HTTPException(400, "A session is already running on this table")

    phone = normalise_phone(body.customer_phone) if body.customer_phone else None
    sess = GameSession(
        table_id=body.table_id,
        club_id=user.club_id,
        customer_name=body.customer_name,
        customer_phone=phone,
        start_time=datetime.utcnow(),
        status="active",
    )
    db.add(sess)

    # Upsert customer profile
    if phone:
        exists = db.query(Customer).filter(
            Customer.club_id == user.club_id, Customer.phone == phone
        ).first()
        if not exists:
            db.add(Customer(club_id=user.club_id, name=body.customer_name, phone=phone))

    db.commit()
    db.refresh(sess)
    return _session_out(sess, db)


@router.post("/add-item")
def add_item(body: AddItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.table_id == body.table_id,
        GameSession.club_id  == user.club_id,
        GameSession.status   == "active",
    ).first()
    if not sess:
        raise HTTPException(404, "No active session on this table")

    menu_item = db.query(MenuItem).filter(
        MenuItem.id == body.item_id, MenuItem.club_id == user.club_id
    ).first()
    if not menu_item:
        raise HTTPException(404, "Menu item not found")

    existing = db.query(SessionItem).filter(
        SessionItem.session_id == sess.id, SessionItem.item_id == body.item_id
    ).first()
    if existing:
        existing.quantity += body.quantity
    else:
        db.add(SessionItem(
            session_id=sess.id,
            item_id=body.item_id,
            item_name=menu_item.name,
            quantity=body.quantity,
            price=menu_item.price,
        ))
    db.commit()
    return _session_out(sess, db)


@router.post("/end")
def end_session(body: EndSessionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.table_id == body.table_id,
        GameSession.club_id  == user.club_id,
        GameSession.status   == "active",
    ).first()
    if not sess:
        raise HTTPException(404, "No active session on this table")

    sess.end_time = datetime.utcnow()
    table = db.query(Table).filter(Table.id == body.table_id).first()
    duration_hrs = (sess.end_time - sess.start_time).total_seconds() / 3600

    sess.game_amount  = round(duration_hrs * table.price_per_hour, 2)
    items = db.query(SessionItem).filter(SessionItem.session_id == sess.id).all()
    sess.snack_amount = round(sum(i.price * i.quantity for i in items), 2)
    sess.total_amount = round(sess.game_amount + sess.snack_amount, 2)
    sess.status = "pending"
    db.commit()
    return _session_out(sess, db)


@router.post("/finalise")
def finalise_session(body: FinaliseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.id      == body.session_id,
        GameSession.club_id == user.club_id,
        GameSession.status  == "pending",
    ).first()
    if not sess:
        raise HTTPException(404, "Pending session not found")

    # Apply snack quantity edits
    if body.snack_edits:
        for edit in body.snack_edits:
            si = db.query(SessionItem).filter(
                SessionItem.session_id == sess.id,
                SessionItem.item_id    == edit.item_id,
            ).first()
            if si:
                if edit.quantity <= 0:
                    db.delete(si)
                else:
                    si.quantity = edit.quantity

    db.flush()
    items = db.query(SessionItem).filter(SessionItem.session_id == sess.id).all()
    sess.snack_amount = round(sum(i.price * i.quantity for i in items), 2)
    sess.total_amount = round((sess.game_amount or 0) + sess.snack_amount, 2)

    if body.override_amount is not None:
        sess.override_amount = body.override_amount
        sess.total_amount    = round(body.override_amount, 2)

    sess.payment_method = body.payment_method
    sess.status         = "pay_later" if body.payment_method == "pay_later" else "collected"
    sess.is_finalized   = True
    db.commit()
    return _session_out(sess, db)


@router.get("")
def list_sessions(
    status: Optional[str] = Query(None),
    user:   User          = Depends(get_current_user),
    db:     Session       = Depends(get_db),
):
    q = db.query(GameSession).filter(GameSession.club_id == user.club_id)
    if status:
        q = q.filter(GameSession.status == status)
    sessions = q.order_by(GameSession.start_time.desc()).all()
    return [_session_out(s, db) for s in sessions]


@router.get("/{session_id}")
def get_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.id == session_id, GameSession.club_id == user.club_id
    ).first()
    if not sess:
        raise HTTPException(404, "Session not found")
    return _session_out(sess, db)


# ── Patch phone on a pending session (used by pay-later flow) ─────────────

from pydantic import BaseModel as _BM

class _PhoneIn(_BM):
    phone: str

@router.patch("/{session_id}/phone")
def patch_phone(session_id: int, body: _PhoneIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.id      == session_id,
        GameSession.club_id == user.club_id,
        GameSession.status  == "pending",
    ).first()
    if not sess:
        raise HTTPException(404, "Pending session not found")
    from app.deps import normalise_phone
    sess.customer_phone = normalise_phone(body.phone)
    db.commit()
    return {"ok": True}
