"""Personal collections (records, books, movies — anything Russell should remember)."""
from fastapi import APIRouter, HTTPException

from core.db import db
from core.models import (
    Collection,
    CollectionCreate,
    CollectionItem,
    CollectionItemCreate,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("")
async def list_collections():
    return await db.collections.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("", response_model=Collection)
async def create_collection(c: CollectionCreate):
    col = Collection(**c.model_dump())
    await db.collections.insert_one(col.model_dump())
    return col


@router.get("/{collection_id}")
async def get_collection(collection_id: str):
    doc = await db.collections.find_one({"id": collection_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Collection not found")
    return doc


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    result = await db.collections.delete_one({"id": collection_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}


@router.post("/{collection_id}/items", response_model=CollectionItem)
async def add_collection_item(collection_id: str, item: CollectionItemCreate):
    new_item = CollectionItem(**item.model_dump())
    result = await db.collections.update_one(
        {"id": collection_id},
        {"$push": {"items": new_item.model_dump()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Collection not found")
    return new_item


@router.delete("/{collection_id}/items/{item_id}")
async def delete_collection_item(collection_id: str, item_id: str):
    result = await db.collections.update_one(
        {"id": collection_id},
        {"$pull": {"items": {"id": item_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(404, "Item not found")
    return {"deleted": True}
