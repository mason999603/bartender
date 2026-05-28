"""Cocktails CRUD + search."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from core.db import db
from core.models import (
    Cocktail,
    CocktailCreate,
    FlavourQuery,
    IngredientsQuery,
)

router = APIRouter(prefix="/cocktails", tags=["cocktails"])


@router.get("")
async def list_cocktails(search: str = "", category: str = "", tag: str = ""):
    query: Dict[str, Any] = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    if category:
        query["category"] = category
    if tag:
        query["tags"] = tag
    docs = await db.cocktails.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return docs


@router.get("/{cocktail_id}")
async def get_cocktail(cocktail_id: str):
    doc = await db.cocktails.find_one({"id": cocktail_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Cocktail not found")
    return doc


@router.post("", response_model=Cocktail)
async def create_cocktail(c: CocktailCreate):
    cocktail = Cocktail(**c.model_dump(), is_custom=True)
    await db.cocktails.insert_one(cocktail.model_dump())
    return cocktail


@router.delete("/{cocktail_id}")
async def delete_cocktail(cocktail_id: str):
    result = await db.cocktails.delete_one({"id": cocktail_id, "is_custom": True})
    if result.deleted_count == 0:
        raise HTTPException(404, "Cocktail not found or not deletable")
    return {"deleted": True}


@router.post("/search-by-ingredients")
async def search_by_ingredients(q: IngredientsQuery):
    """Return cocktails that can be made with the provided ingredients (allowing partial matches)."""
    if not q.ingredients:
        return []
    avail_lower = [i.lower().strip() for i in q.ingredients]
    docs = await db.cocktails.find({}, {"_id": 0}).to_list(1000)

    def matches(ing_name: str) -> bool:
        n = ing_name.lower()
        return any(a in n or n in a for a in avail_lower)

    scored = []
    for d in docs:
        needed = d.get("ingredients", [])
        if not needed:
            continue
        have = [matches(i["name"]) for i in needed]
        match_count = sum(have)
        ratio = match_count / len(needed)
        if ratio >= 0.7:
            missing = [i["name"] for i, h in zip(needed, have) if not h]
            scored.append({
                "cocktail": d,
                "match_ratio": round(ratio, 2),
                "missing": missing,
            })
    scored.sort(key=lambda x: (-x["match_ratio"], x["cocktail"]["name"]))
    return scored


@router.post("/by-flavour")
async def by_flavour(q: FlavourQuery):
    """Search cocktails by flavour profile."""
    include = [f.lower().strip() for f in q.include if f.strip()]
    exclude = [f.lower().strip() for f in q.exclude if f.strip()]
    if not include and not exclude:
        return []

    docs = await db.cocktails.find({}, {"_id": 0}).to_list(1000)

    def has_flavour(profile_terms, target):
        return any(target in p or p in target for p in profile_terms)

    scored = []
    for d in docs:
        profile = [p.lower() for p in d.get("flavor_profile", [])]
        if not profile:
            continue
        inc = sum(1 for f in include if has_flavour(profile, f))
        exc = sum(1 for f in exclude if has_flavour(profile, f))
        if include and inc == 0:
            continue
        if exc > 0:
            continue
        scored.append({
            "cocktail": d,
            "include_matches": inc,
            "matched_flavours": [f for f in include if has_flavour(profile, f)],
        })
    scored.sort(key=lambda x: (-x["include_matches"], x["cocktail"]["name"]))
    return scored[: q.limit]
