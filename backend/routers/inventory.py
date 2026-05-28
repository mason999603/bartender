"""Inventory (in-stock / 86'd ingredients)."""
from fastapi import APIRouter, HTTPException

from core.db import db
from core.models import InventoryCreate, InventoryItem

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("")
async def list_inventory():
    return await db.inventory.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("", response_model=InventoryItem)
async def create_inventory(i: InventoryCreate):
    item = InventoryItem(**i.model_dump())
    await db.inventory.insert_one(item.model_dump())
    return item


@router.patch("/{item_id}")
async def toggle_inventory(item_id: str, in_stock: bool):
    result = await db.inventory.update_one({"id": item_id}, {"$set": {"in_stock": in_stock}})
    if result.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"updated": True}


@router.delete("/{item_id}")
async def delete_inventory(item_id: str):
    result = await db.inventory.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}
