"""Bar tools — compatibility, ABV, batching, cost."""
from typing import List

from fastapi import APIRouter, HTTPException

from core.brain import get_clash_warnings
from core.db import db
from core.models import (
    AbvRequest,
    BatchRequest,
    CocktailIngredient,
    CompatibilityQuery,
    CostRequest,
)

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/compatibility")
async def compatibility(q: CompatibilityQuery):
    warnings = await get_clash_warnings(q.ingredients)
    return {
        "ingredients": q.ingredients,
        "warnings": warnings,
        "verdict": "fatal" if any(w["severity"] == "fatal" for w in warnings)
                   else ("warning" if warnings else "ok"),
    }


@router.post("/abv")
async def abv_calc(req: AbvRequest):
    """Estimated final ABV after dilution."""
    total_volume = sum(i.amount_ml for i in req.ingredients) + req.dilution_ml
    if total_volume == 0:
        return {"abv": 0, "total_volume_ml": 0}
    alcohol_ml = sum(i.amount_ml * (i.abv / 100.0) for i in req.ingredients)
    final_abv = (alcohol_ml / total_volume) * 100
    return {
        "alcohol_ml": round(alcohol_ml, 2),
        "total_volume_ml": round(total_volume, 2),
        "abv": round(final_abv, 2),
        "standard_drinks_au": round(alcohol_ml * 0.789 / 10, 2),
    }


@router.post("/batch")
async def batch_calc(req: BatchRequest):
    """Scale a recipe up."""
    ingredients: List[CocktailIngredient] = []
    if req.cocktail_id:
        doc = await db.cocktails.find_one({"id": req.cocktail_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "Cocktail not found")
        ingredients = [CocktailIngredient(**i) for i in doc.get("ingredients", [])]
    elif req.ingredients:
        ingredients = req.ingredients
    else:
        raise HTTPException(400, "Provide cocktail_id or ingredients")

    scaled = []
    total_single = 0.0
    for ing in ingredients:
        amt = ing.amount_ml * req.servings
        total_single += ing.amount_ml
        scaled.append({"name": ing.name, "amount_ml": round(amt, 1), "notes": ing.notes})

    dilution_water_ml = round(total_single * req.servings * (req.dilution_pct / 100.0), 1)
    total_volume = round(total_single * req.servings + dilution_water_ml, 1)

    return {
        "servings": req.servings,
        "scaled_ingredients": scaled,
        "added_dilution_water_ml": dilution_water_ml,
        "total_volume_ml": total_volume,
        "tip": "For pre-batched stirred drinks, add 20-25% water to mimic stir dilution. Shaken drinks → serve to order.",
    }


@router.post("/cost")
async def cost_calc(req: CostRequest):
    line_items = []
    total = 0.0
    for ing in req.ingredients:
        cost = (ing.amount_ml / 1000.0) * ing.price_per_litre
        total += cost
        line_items.append({
            "name": ing.name,
            "amount_ml": ing.amount_ml,
            "cost": round(cost, 2),
        })
    total += req.extra_cost
    return {
        "line_items": line_items,
        "extra_cost": req.extra_cost,
        "total_cost": round(total, 2),
        "suggested_menu_price_4x": round(total * 4, 2),
        "suggested_menu_price_5x": round(total * 5, 2),
        "note": "Standard pour-cost target is 18-22% (i.e., 4.5x-5.5x raw cost).",
    }
