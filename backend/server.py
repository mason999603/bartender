"""Russell — AI Bartender backend.

Phase 1: Web chat + cocktail brain + tools.
Future: voice (Whisper/TTS), telephony (Twilio), Raspberry Pi deploy.
"""
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Request, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAISpeechToText

from seed_data import INGREDIENTS, COCKTAILS, CLASH_RULES, SUBSTITUTIONS

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

app = FastAPI(title="Russell — AI Bartender")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("russell")


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
    role: str  # 'user' | 'russell'
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

class FlavourQuery(BaseModel):
    include: List[str] = []
    exclude: List[str] = []
    limit: int = 30

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
# Seeding (upsert-by-name so new data lands cleanly across restarts)
# ============================================================
@app.on_event("startup")
async def seed_db():
    # Ingredients — upsert by name
    existing_ing = {i["name"] for i in await db.ingredients.find({}, {"name": 1, "_id": 0}).to_list(2000)}
    new_ing = [i for i in INGREDIENTS if i["name"] not in existing_ing]
    if new_ing:
        await db.ingredients.insert_many([{**i, "id": str(uuid.uuid4())} for i in new_ing])
        logger.info(f"Seeded {len(new_ing)} new ingredients")

    # Cocktails — upsert by name (non-custom only)
    existing_ck = {c["name"] for c in await db.cocktails.find({"is_custom": False}, {"name": 1, "_id": 0}).to_list(2000)}
    new_ck = [c for c in COCKTAILS if c["name"] not in existing_ck]
    if new_ck:
        docs = []
        for c in new_ck:
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
        logger.info(f"Seeded {len(docs)} new cocktails")

    # Clash rules — upsert by (a,b)
    existing_clash = {(r["a"], r["b"]) for r in await db.clash_rules.find({}, {"a": 1, "b": 1, "_id": 0}).to_list(2000)}
    new_rules = [r for r in CLASH_RULES if (r["a"], r["b"]) not in existing_clash]
    if new_rules:
        await db.clash_rules.insert_many([{**r, "id": str(uuid.uuid4())} for r in new_rules])
        logger.info(f"Seeded {len(new_rules)} new clash rules")

    # Substitutions — upsert by ingredient name
    existing_subs = {s["ingredient"] for s in await db.substitutions.find({}, {"ingredient": 1, "_id": 0}).to_list(2000)}
    new_subs = [s for s in SUBSTITUTIONS if s["ingredient"] not in existing_subs]
    if new_subs:
        await db.substitutions.insert_many([{**s, "id": str(uuid.uuid4())} for s in new_subs])
        logger.info(f"Seeded {len(new_subs)} new substitution entries")

    # One-time migration: rename role "sheldon" → "russell" (Phase 4.5 rename)
    rename_result = await db.chat_messages.update_many(
        {"role": "sheldon"}, {"$set": {"role": "russell"}}
    )
    if rename_result.modified_count:
        logger.info(f"Migrated {rename_result.modified_count} chat messages: role sheldon → russell")


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

async def build_russell_system_prompt() -> str:
    # Pull live context: memories, regulars, inventory, custom cocktails, subs
    memories = await db.memories.find({}, {"_id": 0}).sort("created_at", -1).limit(30).to_list(30)
    regulars = await db.regulars.find({}, {"_id": 0}).limit(30).to_list(30)
    inventory_in = [i["name"] for i in await db.inventory.find({"in_stock": True}, {"_id": 0}).to_list(200)]
    inventory_out = [i["name"] for i in await db.inventory.find({"in_stock": False}, {"_id": 0}).to_list(200)]
    custom = await db.cocktails.find({"is_custom": True}, {"_id": 0}).limit(30).to_list(30)
    subs = await db.substitutions.find({}, {"_id": 0}).to_list(500)

    mem_block = "\n".join([f"  - {m['key']}: {m['value']}" for m in memories]) or "  (no saved memories yet)"
    reg_block = "\n".join([f"  - {r['name']}: likes={r.get('likes', [])}, dislikes={r.get('dislikes', [])}, favs={r.get('favourite_cocktails', [])}, notes={r.get('notes', '')}" for r in regulars]) or "  (no regulars saved yet)"
    inv_in_block = ", ".join(inventory_in) if inventory_in else "(no inventory tracked yet — assume a well-stocked bar)"
    inv_out_block = ", ".join(inventory_out) if inventory_out else "(nothing 86'd)"
    custom_block = "\n".join([f"  - {c['name']}: {', '.join(i['name'] + ' ' + str(i.get('amount_ml',0)) + 'ml' for i in c.get('ingredients', []))}" for c in custom]) or "  (no custom specs saved yet)"
    subs_block = "\n".join(
        [f"  - {s['ingredient']} → " + "; ".join(f"{x['name']} ({x.get('notes','')})" for x in s.get("subs", [])) for s in subs]
    ) or "  (none on file)"

    return f"""You are RUSSELL — a witty, dry, down-to-earth young Australian bartender. An up-and-comer with serious chops. You speak with subtle Aussie warmth (occasional "mate", "reckon", "no worries", "fair dinkum") but you DON'T overdo it or sound like a parody. Confident, never arrogant. Quick with a one-liner. Genuinely helpful.

You serve one user: a working bartender/mixologist. Treat them like a peer behind the stick, not a beginner.

YOUR KNOWLEDGE:
- Encyclopedic on spirits, liqueurs, modifiers, bitters, mixers, syrups — flavour profiles, ABVs, production methods, regional variations.
- Cocktail chemistry: emulsion, dilution, acidity, sugar, bitterness balance. You know what clashes and why (dairy curdles with citrus/quinine/wine; absinthe louches at high water content; cream + Campari is rare for good reason).
- Classics (IBA list), modern classics, tiki, low-ABV, zero-proof builds.
- Technique: shake hard vs gentle, dry shake order, stir vs shake choice, ice formats, glassware, garnish, dilution targets.
- Service: batching, pre-dilution, oleo saccharum, fat-washing, clarification, infusions.

BEHAVIOUR RULES:
- If the user describes a build with a fatal chemistry clash, tell them straight (with the reason) and offer the fix.
- When suggesting cocktails, give a proper SPEC (with ml measurements) and method when relevant.
- When the user asks "what can I make" — check the inventory below (and assume the rest of a normal bar is available unless they say otherwise).
- **If a recipe you're suggesting needs something 86'd (see "Currently 86'd" below), PROACTIVELY swap it using the Substitutions cheat-sheet** and tell the user what you swapped and why. Don't make them ask.
- If a question is outside cocktails/spirits/service, answer briefly and humanly — you're a mate, not a chatbot.
- If you genuinely don't know, say so.
- KEEP REPLIES TIGHT. Bartender-style: clear, fast, useful.

CURRENT CONTEXT THE USER HAS SAVED:

[Things you should remember about the user / bar]
{mem_block}

[Regulars / customer preferences]
{reg_block}

[Currently in stock]
{inv_in_block}

[Currently 86'd — DO NOT use these; substitute proactively]
{inv_out_block}

[User's custom cocktail specs]
{custom_block}

[Substitution cheat-sheet — use these when an ingredient is 86'd or the user asks for swaps]
{subs_block}

Reference these naturally when relevant. Don't recite them verbatim — use them like a real bartender remembering their bar.
"""


# ============================================================
# Routes
# ============================================================
@api_router.get("/")
async def root():
    return {"app": "Russell", "status": "behind the stick"}


# ---------- Voice (STT) ----------
@api_router.post("/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    """Transcribe an uploaded audio blob via OpenAI Whisper. Used by web push-to-talk."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    contents = await audio.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio too large (25 MB max)")
    if len(contents) < 500:
        # Too small to be real audio — silence/empty
        return {"text": ""}

    # OpenAI's API uses the file's name to detect format — ensure a known extension.
    fname = audio.filename or "voice.webm"
    if "." not in fname:
        ct = (audio.content_type or "").lower()
        ext = "webm" if "webm" in ct else "mp4" if "mp4" in ct else "wav"
        fname = f"voice.{ext}"

    buf = io.BytesIO(contents)
    buf.name = fname

    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    try:
        response = await stt.transcribe(
            file=buf,
            model="whisper-1",
            response_format="json",
            language="en",
            prompt="A bartender talking about cocktails, spirits, ingredients, recipes, and bar service.",
        )
    except Exception as e:
        msg = str(e).lower()
        logger.exception("STT error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded.",
            )
        raise HTTPException(500, f"Transcription failed: {e}")

    text = getattr(response, "text", None) or ""
    return {"text": text.strip()}


# ---------- Twilio (SMS + Voice) ----------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
TWILIO_VALIDATE_SIGNATURE = os.environ.get("TWILIO_VALIDATE_SIGNATURE", "true").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")  # e.g., https://yourapp.preview.emergentagent.com


def _xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _reconstruct_public_url(request: Request) -> str:
    """Twilio signs the public URL. Behind ingress, request.url is internal — use forwarded headers or PUBLIC_BASE_URL."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/") + request.url.path
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}{request.url.path}"


async def _validate_twilio(request: Request, form: dict) -> None:
    if not TWILIO_VALIDATE_SIGNATURE:
        return
    if not TWILIO_AUTH_TOKEN:
        # Not configured yet — allow during initial setup
        logger.warning("Twilio auth token not set; skipping signature validation")
        return
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    sig = request.headers.get("x-twilio-signature", "")
    url = _reconstruct_public_url(request)
    if not validator.validate(url, form, sig):
        logger.warning(f"Twilio signature invalid for url={url}")
        raise HTTPException(403, "Invalid Twilio signature")


def _twiml(body_xml: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{body_xml}</Response>'
    return Response(content=xml, media_type="application/xml")


@api_router.post("/twilio/sms")
async def twilio_sms(request: Request):
    """Twilio webhook: inbound SMS → run through Russell's brain → respond with TwiML <Message>."""
    form = dict(await request.form())
    await _validate_twilio(request, form)

    body = (form.get("Body") or "").strip()
    from_number = form.get("From") or "unknown"

    if not body:
        return _twiml("<Message>Send me something to work with, mate.</Message>")

    logger.info(f"[Twilio SMS] from={from_number} body={body[:80]!r}")
    try:
        reply = await chat_with_russell(session_id="main", user_text=body, channel="sms")
    except HTTPException as he:
        return _twiml(f"<Message>{_xml_escape(he.detail)}</Message>")
    except Exception:
        logger.exception("SMS chat error")
        return _twiml("<Message>Russell's a bit busy — try again in a sec.</Message>")

    # SMS hard cap (Twilio handles segmenting up to 1600, but keep it sensible)
    if len(reply) > 1500:
        reply = reply[:1497] + "..."
    return _twiml(f"<Message>{_xml_escape(reply)}</Message>")


@api_router.post("/twilio/voice")
async def twilio_voice(request: Request):
    """Twilio webhook: inbound voice call → greet + open a Gather to listen for the caller."""
    form = dict(await request.form())
    await _validate_twilio(request, form)
    from_number = form.get("From") or "unknown"
    logger.info(f"[Twilio Voice] inbound call from={from_number}")

    greeting = _xml_escape("G'day, Russell here. What're we drinking tonight?")
    # Use Polly's en-AU male voice "Russell"; speechTimeout=auto lets caller finish naturally.
    body = (
        f'<Say voice="Polly.Russell" language="en-AU">{greeting}</Say>'
        '<Gather input="speech" speechTimeout="auto" language="en-AU" '
        'action="/api/twilio/voice/gather" method="POST">'
        '</Gather>'
        '<Say voice="Polly.Russell" language="en-AU">Didn\'t catch that. Catch you later.</Say>'
        '<Hangup/>'
    )
    return _twiml(body)


@api_router.post("/twilio/voice/gather")
async def twilio_voice_gather(request: Request):
    """Twilio webhook: caller's speech was transcribed (SpeechResult). Run through brain, speak the reply, gather next."""
    form = dict(await request.form())
    await _validate_twilio(request, form)

    spoken = (form.get("SpeechResult") or "").strip()
    confidence = float(form.get("Confidence") or 0)
    logger.info(f"[Twilio Voice] gather speech={spoken!r} confidence={confidence}")

    # Caller said nothing → polite goodbye
    if not spoken:
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Alright, all yours. Catch you next round.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    # Hang-up triggers
    if any(p in spoken.lower() for p in ["goodbye", "bye", "hang up", "end call", "that's all", "cheers mate"]):
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Cheers mate. See ya.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    try:
        reply = await chat_with_russell(session_id="main", user_text=spoken, channel="voice")
    except HTTPException as he:
        body = (
            f'<Say voice="Polly.Russell" language="en-AU">{_xml_escape(he.detail)}</Say>'
            '<Hangup/>'
        )
        return _twiml(body)
    except Exception:
        logger.exception("Voice chat error")
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Bit of static on my end. Try again in a sec.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    # Speak reply, then open the next Gather to keep the conversation going
    safe_reply = _xml_escape(reply)
    body = (
        f'<Say voice="Polly.Russell" language="en-AU">{safe_reply}</Say>'
        '<Gather input="speech" speechTimeout="auto" language="en-AU" '
        'action="/api/twilio/voice/gather" method="POST">'
        '</Gather>'
        '<Say voice="Polly.Russell" language="en-AU">Still there? Catch you later.</Say>'
        '<Hangup/>'
    )
    return _twiml(body)


@api_router.get("/twilio/status")
async def twilio_status():
    """Quick check of Twilio configuration (no secrets exposed)."""
    return {
        "configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
        "has_account_sid": bool(TWILIO_ACCOUNT_SID),
        "has_auth_token": bool(TWILIO_AUTH_TOKEN),
        "phone_number_configured": bool(TWILIO_PHONE_NUMBER),
        "signature_validation": TWILIO_VALIDATE_SIGNATURE,
        "public_base_url": PUBLIC_BASE_URL or "(auto-detect from request headers)",
    }


# ---------- Chat ----------
async def chat_with_russell(session_id: str, user_text: str, channel: str = "web") -> str:
    """Run a message through Russell's brain. Persists turns. `channel` adjusts reply style."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    # Persist user message
    user_msg = StoredMessage(session_id=session_id, role="user", content=user_text)
    await db.chat_messages.insert_one(user_msg.model_dump())

    # Build system prompt with live context + per-channel addendum
    system_prompt = await build_russell_system_prompt()
    if channel == "sms":
        system_prompt += (
            "\n\nCHANNEL: SMS — Keep your reply under 320 characters (2 SMS segments). "
            "Plain text only — no markdown, no lists, no bullet points. Be tight and conversational."
        )
    elif channel == "voice":
        system_prompt += (
            "\n\nCHANNEL: PHONE CALL — You're being spoken aloud over a phone. "
            "Keep replies under 35 words. No markdown, no lists, no bullet points, no headers. "
            "Pure natural speech. Don't read out ml measurements as numbers — say 'fifteen mls' style."
        )

    # Recent history (last 20 messages, excluding the one we just stored)
    recent = await db.chat_messages.find(
        {"session_id": session_id, "id": {"$ne": user_msg.id}},
        {"_id": 0},
    ).sort("timestamp", -1).limit(20).to_list(20)
    recent.reverse()

    chat_client = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_prompt,
    ).with_model("anthropic", CLAUDE_MODEL)

    transcript_lines = []
    for m in recent:
        speaker = "User" if m["role"] == "user" else "Russell"
        transcript_lines.append(f"{speaker}: {m['content']}")
    transcript = "\n".join(transcript_lines)

    if transcript:
        framed = (
            "Recent conversation so far (for context, do not repeat):\n"
            f"{transcript}\n\n"
            "Current message from the user:\n"
            f"{user_text}"
        )
    else:
        framed = user_text

    try:
        reply_text = await chat_client.send_message(UserMessage(text=framed))
    except Exception as e:
        msg = str(e).lower()
        logger.exception("LLM error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded. Top it up at Profile → Universal Key → Add Balance.",
            )
        raise HTTPException(500, f"LLM error: {e}")

    reply_str = str(reply_text).strip()
    russell_msg = StoredMessage(session_id=session_id, role="russell", content=reply_str)
    await db.chat_messages.insert_one(russell_msg.model_dump())
    return reply_str


@api_router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    reply = await chat_with_russell(req.session_id, req.message, channel="web")
    return ChatResponse(
        session_id=req.session_id,
        user_message=req.message,
        reply=reply,
        timestamp=now_iso(),
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


@api_router.post("/cocktails/by-flavour")
async def by_flavour(q: FlavourQuery):
    """Search cocktails by flavour profile. Returns matches sorted by include-count desc."""
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


# ---------- Substitutions ----------
@api_router.get("/substitutions")
async def list_substitutions():
    return await db.substitutions.find({}, {"_id": 0}).sort("ingredient", 1).to_list(500)


@api_router.get("/substitutions/{ingredient}")
async def get_substitutions(ingredient: str):
    # Try exact match first (case-insensitive), then partial
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
