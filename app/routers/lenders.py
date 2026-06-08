from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User, GameSession, SessionItem, Customer
from app.schemas.schemas import PayLenderIn
from app.deps import get_current_user, normalise_phone

router = APIRouter(tags=["lenders"])


# ── Customer phone lookup ─────────────────────────────────────────────────

@router.get("/customers/lookup")
def lookup_customer(phone: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    norm = normalise_phone(phone)
    if not norm:
        return {"found": False}

    cust = db.query(Customer).filter(
        Customer.club_id == user.club_id, Customer.phone == norm
    ).first()

    unpaid = db.query(GameSession).filter(
        GameSession.club_id        == user.club_id,
        GameSession.customer_phone == norm,
        GameSession.status         == "pay_later",
    ).all()
    debt = round(sum(s.total_amount or 0 for s in unpaid), 2)

    if cust:
        return {"found": True, "name": cust.name, "phone": norm, "outstanding_debt": debt}
    return {"found": False, "phone": norm, "outstanding_debt": debt}


# ── Lenders list ─────────────────────────────────────────────────────────

@router.get("/lenders")
def get_lenders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    unpaid = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "pay_later",
    ).order_by(GameSession.start_time.desc()).all()

    by_key: dict = {}
    for s in unpaid:
        key = s.customer_phone or s.customer_name
        if key not in by_key:
            by_key[key] = {"name": s.customer_name, "phone": s.customer_phone, "total": 0, "bills": []}
        by_key[key]["total"] = round(by_key[key]["total"] + (s.total_amount or 0), 2)

        items = db.query(SessionItem).filter(SessionItem.session_id == s.id).all()
        by_key[key]["bills"].append({
            "id":            s.id,
            "table_id":      s.table_id,
            "start_time":    s.start_time.isoformat() if s.start_time else None,
            "end_time":      s.end_time.isoformat()   if s.end_time   else None,
            "total_amount":  s.total_amount,
            "items": [{"item_name": i.item_name, "quantity": i.quantity, "price": i.price} for i in items],
        })

    return list(by_key.values())


# ── Pay a single lender bill ──────────────────────────────────────────────

@router.post("/lenders/pay")
def pay_lender_bill(body: PayLenderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sess = db.query(GameSession).filter(
        GameSession.id      == body.session_id,
        GameSession.club_id == user.club_id,
        GameSession.status  == "pay_later",
    ).first()
    if not sess:
        raise HTTPException(404, "Pay-later session not found")
    sess.status         = "collected"
    sess.payment_method = body.payment_method
    db.commit()
    return {"ok": True}


# ── Pay all bills for a customer (by phone or name) ───────────────────────

@router.post("/lenders/pay-all")
def pay_all_lender(
    identifier:     str,
    payment_method: str,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    norm = normalise_phone(identifier)
    sessions = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "pay_later",
    ).filter(
        (GameSession.customer_phone == norm) | (GameSession.customer_name == identifier)
    ).all()

    if not sessions:
        raise HTTPException(404, "No pay-later sessions found for this customer")

    for s in sessions:
        s.status         = "collected"
        s.payment_method = payment_method
    db.commit()
    return {"paid": len(sessions)}
