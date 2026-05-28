"""Sheldon — AI Bartender backend.

Phase 1: Web chat + cocktail brain + tools.
Future: voice (Whisper/TTS), telephony (Twilio), Raspberry Pi deploy.
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage

from seed_data import INGREDIENTS, COCKTAILS, CLASH_RULES

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

app = FastAPI(title="Sheldon — AI Bartender")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("sheldon")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# Models
# ============================================================
class ChatRequest(BaseModel):
    session_id: str = "main"
    message: str

class ChatResponse(BaseModel):
    session_id: str
    user_message: str
    reply: str
    timestamp: str

class StoredMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # 'user' | 'sheldon'
    content: str
    timestamp: str = Field(default_factory=now_iso)

class CocktailIngredient(BaseModel):
    name: str
    amount_ml: float = 0
    notes: Optional[str] = None

class Cocktail(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str = "other"
    glassware: str = ""
    garnish: str = ""
    method: str = ""
    ingredients: List[CocktailIngredient] = []
    instructions: str = ""
    flavor_profile: List[str] = []
    abv_estimate: float = 0
    tags: List[str] = []
    is_custom: bool = False
    created_at: str = Field(default_factory=now_iso)

class CocktailCreate(BaseModel):
    name: str
    category: str = "custom"
    glassware: str = ""
    garnish: str = ""
    method: str = ""
    ingredients: List[CocktailIngredient] = []
    instructions: str = ""
    flavor_profile: List[str] = []
    abv_estimate: float = 0
    tags: List[str] = []

class IngredientsQuery(BaseModel):
    ingredients: List[str]

class CompatibilityQuery(BaseModel):
    ingredients: List[str]

class BatchRequest(BaseModel):
    cocktail_id: Optional[str] = None
    ingredients: Optional[List[CocktailIngredient]] = None
    servings: int = 10
    dilution_pct: float = 0  # for pre-batched stirred drinks add water

class AbvIngredient(BaseModel):
    name: str
    amount_ml: float
    abv: float

class AbvRequest(BaseModel):
    ingredients: List[AbvIngredient]
    dilution_ml: float = 0  # additional water / ice melt

class CostIngredient(BaseModel):
    name: str
    amount_ml: float
    price_per_litre: float  # in user's currency

class CostRequest(BaseModel):
    ingredients: List[CostIngredient]
    extra_cost: float = 0  # garnish, ice, etc.

class Regular(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    likes: List[str] = []
    dislikes: List[str] = []
    favourite_cocktails: List[str] = []
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)

class RegularCreate(BaseModel):
    name: str
    likes: List[str] = []
    dislikes: List[str] = []
    favourite_cocktails: List[str] = []
    notes: str = ""

class Memory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str
    value: str
    created_at: str = Field(default_factory=now_iso)

class MemoryCreate(BaseModel):
    key: str
    value: str

class InventoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    in_stock: bool = True
    notes: str = ""

class InventoryCreate(BaseModel):
    name: str
    in_stock: bool = True
    notes: str = ""


# ============================================================
# Seeding
# ============================================================
@app.on_event("startup")
async def seed_db():
    # Ingredients
    if await db.ingredients.count_documents({}) == 0:
        await db.ingredients.insert_many([{**i, "id": str(uuid.uuid4())} for i in INGREDIENTS])
        logger.info(f"Seeded {len(INGREDIENTS)} ingredients")
    # Cocktails
    if await db.cocktails.count_documents({"is_custom": False}) == 0:
        docs = []
        for c in COCKTAILS:
            docs.append({
                "id": str(uuid.uuid4()),
                "name": c["name"],
                "category": c.get("category", "other"),
                "glassware": c.get("glassware", ""),
                "garnish": c.get("garnish", ""),
                "method": c.get("method", ""),
                "ingredients": c.get("ingredients", []),
                "instructions": c.get("instructions", ""),
                "flavor_profile": c.get("flavor_profile", []),
                "abv_estimate": c.get("abv_estimate", 0),
                "tags": c.get("tags", []),
                "is_custom": False,
                "created_at": now_iso(),
            })
        await db.cocktails.insert_many(docs)
        logger.info(f"Seeded {len(docs)} cocktails")
    # Clash rules
    if await db.clash_rules.count_documents({}) == 0:
        await db.clash_rules.insert_many([{**r, "id": str(uuid.uuid4())} for r in CLASH_RULES])
        logger.info(f"Seeded {len(CLASH_RULES)} clash rules")


@app.on_event("shutdown")
async def shutdown_db():
    client.close()


# ============================================================
# Helpers
# ============================================================
def clean_doc(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc

async def get_clash_warnings(ingredient_names: List[str]) -> List[dict]:
    names_lower = [n.lower() for n in ingredient_names]
    rules = await db.clash_rules.find({}, {"_id": 0}).to_list(1000)
    warnings = []
    for r in rules:
        a, b = r["a"].lower(), r["b"].lower()
        # exact match either direction
        if a in names_lower and b in names_lower:
            warnings.append(r)
            continue
        # partial match for liberal hits (e.g., "cream" matching "Heavy Cream")
        if any(a in n or n in a for n in names_lower) and any(b in n or n in b for n in names_lower):
            if r not in warnings:
                warnings.append(r)
    return warnings

async def build_sheldon_system_prompt() -> str:
    # Pull live context: memories, regulars, inventory in-stock, custom cocktails
    memories = await db.memories.find({}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    regulars = await db.regulars.find({}, {"_id": 0}).limit(30).to_list(30)
    inventory_in = [i["name"] for i in await db.inventory.find({"in_stock": True}, {"_id": 0}).to_list(200)]
    custom = await db.cocktails.find({"is_custom": True}, {"_id": 0}).limit(30).to_list(30)

    mem_block = "\n".join([f"  - {m['key']}: {m['value']}" for m in memories]) or "  (no saved memories yet)"
    reg_block = "\n".join([f"  - {r['name']}: likes={r.get('likes', [])}, dislikes={r.get('dislikes', [])}, favs={r.get('favourite_cocktails', [])}, notes={r.get('notes', '')}" for r in regulars]) or "  (no regulars saved yet)"
    inv_block = ", ".join(inventory_in) if inventory_in else "(no inventory tracked yet — assume a well-stocked bar)"
    custom_block = "\n".join([f"  - {c['name']}: {', '.join(i['name'] + ' ' + str(i.get('amount_ml',0)) + 'ml' for i in c.get('ingredients', []))}" for c in custom]) or "  (no custom specs saved yet)"

    return f"""You are SHELDON — a witty, dry, down-to-earth young Australian bartender. An up-and-comer with serious chops. You speak with subtle Aussie warmth (occasional "mate", "reckon", "no worries", "fair dinkum") but you DON'T overdo it or sound like a parody. Confident, never arrogant. Quick with a one-liner. Genuinely helpful.

You serve one user: a working bartender/mixologist. Treat them like a peer behind the stick, not a beginner.

YOUR KNOWLEDGE:
- Encyclopedic on spirits, liqueurs, modifiers, bitters, mixers, syrups — their flavour profiles, ABVs, production methods, regional variations.
- Cocktail chemistry: emulsion, dilution, acidity, sugar, bitterness balance. Know what clashes and why (e.g., dairy curdles with citrus/quinine/wine; absinthe lourches at high water content; cream + Campari is rare for good reason).
- Classics (IBA list), modern classics, tiki, low-ABV, zero-proof builds.
- Technique: shake hard vs gentle, dry shake order, stir vs shake choice, ice formats, glassware, garnish, dilution targets.
- Service knowledge: batching, pre-dilution, oleo saccharum, fat-washing, clarification, infusions.

BEHAVIOUR RULES:
- If the user describes a build with a fatal chemistry clash, tell them straight (with the reason) and offer the fix.
- When suggesting cocktails, give a proper SPEC (with ml measurements) and method when relevant.
- When the user asks "what can I make" — check the inventory below (and assume the rest of a normal bar is available unless they say otherwise).
- If a question is outside cocktails/spirits/service, answer it briefly and humanly — you're a mate, not a chatbot.
- If you genuinely don't know, say so.
- KEEP REPLIES TIGHT. No essay-length answers unless asked. Bartender-style: clear, fast, useful.

CURRENT CONTEXT THE USER HAS SAVED:

[Things you should remember about the user / bar]
{mem_block}

[Regulars / customer preferences]
{reg_block}

[Current in-stock inventory]
{inv_block}

[User's custom cocktail specs]
{custom_block}

Reference these naturally when relevant. Don't recite them verbatim — use them like a real bartender remembering their bar.
"""


# ============================================================
# Routes
# ============================================================
@api_router.get("/")
async def root():
    return {"app": "Sheldon", "status": "behind the stick"}


# ---------- Chat ----------
@api_router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    # Persist user message
    user_msg = StoredMessage(session_id=req.session_id, role="user", content=req.message)
    await db.chat_messages.insert_one(user_msg.model_dump())

    # Build system prompt with live context
    system_prompt = await build_sheldon_system_prompt()

    # Recent history (last 20 messages, excluding the one we just stored)
    recent = await db.chat_messages.find(
        {"session_id": req.session_id, "id": {"$ne": user_msg.id}},
        {"_id": 0},
    ).sort("timestamp", -1).limit(20).to_list(20)
    recent.reverse()  # chronological

    # Frame the request with conversation transcript so Claude sees full context.
    chat_client = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=req.session_id,
        system_message=system_prompt,
    ).with_model("anthropic", CLAUDE_MODEL)

    transcript_lines = []
    for m in recent:
        speaker = "User" if m["role"] == "user" else "Sheldon"
        transcript_lines.append(f"{speaker}: {m['content']}")
    transcript = "\n".join(transcript_lines)

    if transcript:
        framed = (
            "Recent conversation so far (for context, do not repeat):\n"
            f"{transcript}\n\n"
            "Current message from the user:\n"
            f"{req.message}"
        )
    else:
        framed = req.message

    try:
        reply_text = await chat_client.send_message(UserMessage(text=framed))
    except Exception as e:
        logger.exception("LLM error")
        raise HTTPException(500, f"LLM error: {e}")

    reply_str = str(reply_text).strip()

    sheldon_msg = StoredMessage(session_id=req.session_id, role="sheldon", content=reply_str)
    await db.chat_messages.insert_one(sheldon_msg.model_dump())

    return ChatResponse(
        session_id=req.session_id,
        user_message=req.message,
        reply=reply_str,
        timestamp=sheldon_msg.timestamp,
    )


@api_router.get("/chat/history")
async def chat_history(session_id: str = "main", limit: int = 100):
    msgs = await db.chat_messages.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(limit)
    return msgs


@api_router.delete("/chat/history")
async def clear_chat(session_id: str = "main"):
    result = await db.chat_messages.delete_many({"session_id": session_id})
    return {"deleted": result.deleted_count}


# ---------- Cocktails ----------
@api_router.get("/cocktails")
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


@api_router.get("/cocktails/{cocktail_id}")
async def get_cocktail(cocktail_id: str):
    doc = await db.cocktails.find_one({"id": cocktail_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Cocktail not found")
    return doc


@api_router.post("/cocktails", response_model=Cocktail)
async def create_cocktail(c: CocktailCreate):
    cocktail = Cocktail(**c.model_dump(), is_custom=True)
    await db.cocktails.insert_one(cocktail.model_dump())
    return cocktail


@api_router.delete("/cocktails/{cocktail_id}")
async def delete_cocktail(cocktail_id: str):
    # Only custom specs can be deleted
    result = await db.cocktails.delete_one({"id": cocktail_id, "is_custom": True})
    if result.deleted_count == 0:
        raise HTTPException(404, "Cocktail not found or not deletable")
    return {"deleted": True}


@api_router.post("/cocktails/search-by-ingredients")
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
        # Skip pure mixers in the count for stricter matching: require at least
        # 70% of ingredients matched
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


# ---------- Ingredients ----------
@api_router.get("/ingredients")
async def list_ingredients(category: str = "", flavor: str = ""):
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    if flavor:
        q["flavor_profile"] = flavor
    docs = await db.ingredients.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    return docs


# ---------- Tools ----------
@api_router.post("/tools/compatibility")
async def compatibility(q: CompatibilityQuery):
    warnings = await get_clash_warnings(q.ingredients)
    return {
        "ingredients": q.ingredients,
        "warnings": warnings,
        "verdict": "fatal" if any(w["severity"] == "fatal" for w in warnings)
                   else ("warning" if warnings else "ok"),
    }


@api_router.post("/tools/abv")
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
        "standard_drinks_au": round(alcohol_ml * 0.789 / 10, 2),  # AU = 10g alcohol
    }


@api_router.post("/tools/batch")
async def batch_calc(req: BatchRequest):
    """Scale a recipe up. Returns scaled volumes per ingredient + total volume + recommended dilution water."""
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


@api_router.post("/tools/cost")
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


# ---------- Regulars ----------
@api_router.get("/regulars")
async def list_regulars():
    return await db.regulars.find({}, {"_id": 0}).sort("name", 1).to_list(500)

@api_router.post("/regulars", response_model=Regular)
async def create_regular(r: RegularCreate):
    reg = Regular(**r.model_dump())
    await db.regulars.insert_one(reg.model_dump())
    return reg

@api_router.delete("/regulars/{regular_id}")
async def delete_regular(regular_id: str):
    result = await db.regulars.delete_one({"id": regular_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}


# ---------- Memory ----------
@api_router.get("/memory")
async def list_memory():
    return await db.memories.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api_router.post("/memory", response_model=Memory)
async def create_memory(m: MemoryCreate):
    mem = Memory(**m.model_dump())
    await db.memories.insert_one(mem.model_dump())
    return mem

@api_router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    result = await db.memories.delete_one({"id": memory_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}


# ---------- Inventory ----------
@api_router.get("/inventory")
async def list_inventory():
    return await db.inventory.find({}, {"_id": 0}).sort("name", 1).to_list(500)

@api_router.post("/inventory", response_model=InventoryItem)
async def create_inventory(i: InventoryCreate):
    item = InventoryItem(**i.model_dump())
    await db.inventory.insert_one(item.model_dump())
    return item

@api_router.patch("/inventory/{item_id}")
async def toggle_inventory(item_id: str, in_stock: bool):
    result = await db.inventory.update_one({"id": item_id}, {"$set": {"in_stock": in_stock}})
    if result.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"updated": True}

@api_router.delete("/inventory/{item_id}")
async def delete_inventory(item_id: str):
    result = await db.inventory.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"deleted": True}


# Mount router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
