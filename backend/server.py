"""Russell — AI Bartender backend.

Thin FastAPI app shell: lifecycle (seed/migrate/shutdown), CORS, and router mounting.
All endpoints live under `/app/backend/routers/`. Shared infra in `/app/backend/core/`.
"""
import logging
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from pathlib import Path
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from core.config import CORS_ORIGINS  # noqa: E402
from core.db import client, db  # noqa: E402
from core.models import now_iso  # noqa: E402
from seed_data import CLASH_RULES, COCKTAILS, INGREDIENTS, SUBSTITUTIONS  # noqa: E402

from routers import (  # noqa: E402
    chat,
    cocktails,
    collections,
    companion,
    ingredients,
    inventory,
    memory,
    regulars,
    spotify_routes,
    substitutions,
    telegram_routes,
    tools,
    twilio_routes,
    voice,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("russell")

app = FastAPI(title="Russell — AI Bartender")
api_router = APIRouter(prefix="/api")


@app.on_event("startup")
async def seed_db():
    # Ingredients — upsert by name
    existing_ing = {i["name"] for i in await db.ingredients.find({}, {"name": 1, "_id": 0}).to_list(2000)}
    new_ing = [i for i in INGREDIENTS if i["name"] not in existing_ing]
    if new_ing:
        await db.ingredients.insert_many([{**i, "id": str(uuid.uuid4())} for i in new_ing])
        logger.info(f"Seeded {len(new_ing)} new ingredients")

    # Cocktails — upsert by name (non-custom only), skipping any user-deleted seeds.
    existing_ck = {c["name"] for c in await db.cocktails.find({"is_custom": False}, {"name": 1, "_id": 0}).to_list(2000)}
    tombstoned = {t["name"] for t in await db.deleted_seeds.find({}, {"name": 1, "_id": 0}).to_list(2000)}
    new_ck = [c for c in COCKTAILS if c["name"] not in existing_ck and c["name"] not in tombstoned]
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

    # Content migration: rewrite "Sheldon" → "Russell" inside historical message bodies (any role).
    content_result = await db.chat_messages.update_many(
        {"content": {"$regex": "[Ss]heldon"}},
        [{
            "$set": {
                "content": {
                    "$replaceAll": {
                        "input": {"$replaceAll": {"input": "$content", "find": "Sheldon", "replacement": "Russell"}},
                        "find": "sheldon",
                        "replacement": "russell",
                    }
                }
            }
        }],
    )
    if content_result.modified_count:
        logger.info(f"Rewrote 'Sheldon' → 'Russell' in {content_result.modified_count} historical messages")


@app.on_event("shutdown")
async def shutdown_db():
    client.close()


@api_router.get("/")
async def root():
    return {"app": "Russell", "status": "behind the stick"}


# Mount feature routers under /api
for r in (
    chat.router,
    voice.router,
    companion.router,
    twilio_routes.router,
    cocktails.router,
    substitutions.router,
    ingredients.router,
    tools.router,
    regulars.router,
    memory.router,
    inventory.router,
    collections.router,
    spotify_routes.router,
    telegram_routes.router,
):
    api_router.include_router(r)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
