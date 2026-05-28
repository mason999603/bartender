"""Regulars CRUD."""
from fastapi import APIRouter, HTTPException

from core.db import db
from core.models import Regular, RegularCreate

router = APIRouter(prefix="/regulars", tags=["regulars"])


@router.get("")
async def list_regulars():
    return await db.regulars.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("", response_model=Regular)
async def create_regular(r: RegularCreate):
    reg = Regular(**r.model_dump())
    await db.regulars.insert_one(reg.model_dump())
    return reg


@router.delete("/{regular_id}")
async def delete_regular(regular_id: str):
    result = await db.regulars.delete_one({"id": regular_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}
