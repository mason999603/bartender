"""Ingredients lookup."""
from typing import Any, Dict

from fastapi import APIRouter

from core.db import db

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("")
async def list_ingredients(category: str = "", flavor: str = ""):
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    if flavor:
        q["flavor_profile"] = flavor
    docs = await db.ingredients.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    return docs
