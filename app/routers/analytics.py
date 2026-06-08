from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, date
import json

from app.db.session import get_db
from app.models.models import User, Table, GameSession, SessionItem, Booking, DayClose
from app.schemas.schemas import DayCloseIn
from app.deps import get_current_user
from fastapi import HTTPException

router = APIRouter(tags=["analytics"])


# ── Dashboard summary ─────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today_str = date.today().isoformat()

    active_count = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "active",
    ).count()

    today_collected = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "collected",
        func.date(GameSession.end_time) == today_str,
    ).all()
    today_rev = round(sum(s.total_amount or 0 for s in today_collected), 2)

    pending_bookings = db.query(Booking).filter(
        Booking.club_id     == user.club_id,
        Booking.booked_date == today_str,
        Booking.status      == "pending",
    ).count()

    unpaid_lenders = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "pay_later",
    ).count()

    return {
        "active_sessions":  active_count,
        "today_revenue":    today_rev,
        "today_sessions":   len(today_collected),
        "pending_bookings": pending_bookings,
        "unpaid_lenders":   unpaid_lenders,
    }


# ── Analytics ─────────────────────────────────────────────────────────────

@router.get("/analytics")
def analytics(
    range_days: int   = Query(30, ge=1, le=365),
    user:       User  = Depends(get_current_user),
    db:         Session = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=range_days)
    sessions = db.query(GameSession).filter(
        GameSession.club_id     == user.club_id,
        GameSession.status.in_(["collected", "pay_later"]),
        GameSession.start_time  >= cutoff,
    ).all()

    tables = {t.id: t.table_name for t in db.query(Table).filter(Table.club_id == user.club_id).all()}

    collected = [s for s in sessions if s.status == "collected"]
    pending   = [s for s in sessions if s.status == "pay_later"]

    collected_rev = round(sum(s.total_amount or 0 for s in collected), 2)
    pending_amt   = round(sum(s.total_amount or 0 for s in pending),   2)
    game_rev      = round(sum(s.game_amount  or 0 for s in collected), 2)
    snack_rev     = round(sum(s.snack_amount or 0 for s in collected), 2)

    by_table: dict = {}
    for s in sessions:
        name = tables.get(s.table_id, "Unknown")
        by_table[name] = round(by_table.get(name, 0) + (s.total_amount or 0), 2)

    best_table = max(by_table, key=by_table.get) if by_table else None

    by_customer: dict = {}
    for s in sessions:
        key = s.customer_phone or s.customer_name or "Unknown"
        if key not in by_customer:
            by_customer[key] = {"name": s.customer_name, "sessions": 0, "total": 0}
        by_customer[key]["sessions"] += 1
        by_customer[key]["total"]    = round(by_customer[key]["total"] + (s.total_amount or 0), 2)

    top_customers = sorted(by_customer.values(), key=lambda x: x["total"], reverse=True)[:5]

    # Table utilisation: hours played per table in the period
    utilisation: dict = {}
    for s in sessions:
        name = tables.get(s.table_id, "Unknown")
        if s.end_time and s.start_time:
            hrs = (s.end_time - s.start_time).total_seconds() / 3600
            utilisation[name] = round(utilisation.get(name, 0) + hrs, 2)

    # Available hours = range_days * 12 hrs/day (configurable)
    hours_per_day = 12
    total_available = range_days * hours_per_day
    utilisation_pct = {
        name: round((hrs / total_available) * 100, 1)
        for name, hrs in utilisation.items()
    }

    # Average session duration in minutes
    durations = [
        (s.end_time - s.start_time).total_seconds() / 60
        for s in sessions if s.end_time and s.start_time
    ]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    return {
        "collected_revenue": collected_rev,
        "pending_amount":    pending_amt,
        "total_sessions":    len(sessions),
        "best_table":        best_table,
        "game_revenue":      game_rev,
        "snack_revenue":     snack_rev,
        "by_table":          by_table,
        "top_customers":     top_customers,
        "utilisation_hours": utilisation,
        "utilisation_pct":   utilisation_pct,
        "avg_duration_mins": avg_duration,
    }


# ── Day Close ─────────────────────────────────────────────────────────────

@router.post("/day-close")
def create_day_close(body: DayCloseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    active = db.query(GameSession).filter(
        GameSession.club_id == user.club_id,
        GameSession.status  == "active",
    ).count()
    if active:
        raise HTTPException(400, f"{active} session(s) still active — end them before closing the day")

    sessions = db.query(GameSession).filter(
        GameSession.club_id     == user.club_id,
        GameSession.status.in_(["collected", "pay_later"]),
        func.date(GameSession.end_time) == body.close_date,
    ).all()

    cash    = round(sum(s.total_amount or 0 for s in sessions if s.payment_method == "cash"),  2)
    upi     = round(sum(s.total_amount or 0 for s in sessions if s.payment_method == "upi"),   2)
    card    = round(sum(s.total_amount or 0 for s in sessions if s.payment_method == "card"),  2)
    pending = round(sum(s.total_amount or 0 for s in sessions if s.status == "pay_later"),     2)

    snack_totals: dict = {}
    for s in sessions:
        for si in db.query(SessionItem).filter(SessionItem.session_id == s.id).all():
            key = si.item_name or "?"
            snack_totals[key] = round(snack_totals.get(key, 0) + si.price * si.quantity, 2)

    tables   = {t.id: t.table_name for t in db.query(Table).filter(Table.club_id == user.club_id).all()}
    by_table = {}
    for s in sessions:
        name = tables.get(s.table_id, "Unknown")
        by_table[name] = round(by_table.get(name, 0) + (s.total_amount or 0), 2)

    summary = {
        "close_date":     body.close_date,
        "total_sessions": len(sessions),
        "cash":           cash,
        "upi":            upi,
        "card":           card,
        "pending":        pending,
        "gross_total":    round(cash + upi + card + pending, 2),
        "snacks":         snack_totals,
        "by_table":       by_table,
    }

    dc = DayClose(
        club_id        = user.club_id,
        close_date     = body.close_date,
        summary_json   = json.dumps(summary),
        total_revenue  = round(cash + upi + card, 2),
        cash_revenue   = cash,
        upi_revenue    = upi,
        card_revenue   = card,
        pending_amount = pending,
        total_sessions = len(sessions),
    )
    db.add(dc)
    db.commit()
    return summary


@router.get("/day-close")
def list_day_closes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    closes = db.query(DayClose).filter(
        DayClose.club_id == user.club_id
    ).order_by(DayClose.close_date.desc()).all()
    return [
        {
            "id":             c.id,
            "close_date":     c.close_date,
            "total_revenue":  c.total_revenue,
            "total_sessions": c.total_sessions,
            "summary":        json.loads(c.summary_json),
        }
        for c in closes
    ]
