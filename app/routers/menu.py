from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.models import User, MenuItem
from app.schemas.schemas import MenuItemIn
from app.deps import get_current_user

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("")
def list_menu(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(MenuItem).filter(MenuItem.club_id == user.club_id).order_by(
        MenuItem.category, MenuItem.name
    ).all()
    return [
        {"id": i.id, "name": i.name, "price": i.price, "category": i.category or "General"}
        for i in items
    ]


@router.get("/categories")
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns distinct category names for this club, sorted alphabetically."""
    rows = db.query(MenuItem.category).filter(
        MenuItem.club_id == user.club_id
    ).distinct().all()
    cats = sorted({r.category or "General" for r in rows})
    return cats


@router.post("")
def create_menu_item(body: MenuItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = MenuItem(
        name=body.name,
        price=body.price,
        category=body.category or "General",
        club_id=user.club_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name, "price": item.price, "category": item.category}


@router.put("/{item_id}")
def update_menu_item(item_id: int, body: MenuItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.club_id == user.club_id).first()
    if not item:
        raise HTTPException(404, "Menu item not found")
    item.name     = body.name
    item.price    = body.price
    item.category = body.category or "General"
    db.commit()
    return {"id": item.id, "name": item.name, "price": item.price, "category": item.category}


@router.delete("/{item_id}")
def delete_menu_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.club_id == user.club_id).first()
    if not item:
        raise HTTPException(404, "Menu item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}