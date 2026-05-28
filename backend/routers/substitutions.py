"""Substitutions lookup."""
from fastapi import APIRouter, HTTPException

from core.db import db

router = APIRouter(prefix="/substitutions", tags=["substitutions"])


@router.get("")
async def list_substitutions():
    return await db.substitutions.find({}, {"_id": 0}).sort("ingredient", 1).to_list(500)


@router.get("/{ingredient}")
async def get_substitutions(ingredient: str):
    doc = await db.substitutions.find_one(
        {"ingredient": {"$regex": f"^{ingredient}$", "$options": "i"}}, {"_id": 0}
    )
    if not doc:
        doc = await db.substitutions.find_one(
            {"ingredient": {"$regex": ingredient, "$options": "i"}}, {"_id": 0}
        )
    if not doc:
        raise HTTPException(
            404,
            "No substitutions on file for that one. Ask Russell in chat — he'll improvise."
        )
    return doc
