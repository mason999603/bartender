"""Memory (key/value notes Russell should remember)."""
from fastapi import APIRouter, HTTPException

from core.db import db
from core.models import Memory, MemoryCreate

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
async def list_memory():
    return await db.memories.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("", response_model=Memory)
async def create_memory(m: MemoryCreate):
    mem = Memory(**m.model_dump())
    await db.memories.insert_one(mem.model_dump())
    return mem


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    result = await db.memories.delete_one({"id": memory_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}
