"""Evergreen cocktail-content topic rotator.

Russell picks tomorrow's topic from this list every night. When the list is
exhausted (60 days), it cycles from the top. New topics can be added to
`db.autopilot_topics` at any time — those take priority over the seed list.

Storage:
    db.autopilot_state (_id="primary"):
        cursor  — current index into the effective topic list
        last_topic — the last one Russell used (avoids repeats on manual triggers)
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

# 60 evergreen hooks — deliberately opinionated so Russell always has something to say.
SEED_TOPICS = [
    "How to shake a whisky sour properly (the dry-shake myth)",
    "Why cheap bourbon makes a better Old Fashioned than premium",
    "The Negroni ratio nobody teaches (it's not 1:1:1)",
    "Muddling fruit in an Old Fashioned is a red flag",
    "Vermouth belongs in the fridge — here's why yours went off",
    "The Espresso Martini is a bad drink and here's how to fix it",
    "Egg white in a cocktail: technique, not garnish",
    "Ice: your bar's single biggest quality upgrade",
    "How to build a home bar for under $200",
    "The Margarita ratio that actually works",
    "Every Aperol Spritz is too sweet — the fix",
    "Why bartenders hate the Long Island Iced Tea",
    "Bitters are the salt of cocktails — here's how to use them",
    "The Manhattan is not a whiskey drink",
    "Fat-washing whisky at home in 90 seconds",
    "The Daiquiri is a test — most bars fail it",
    "How to batch cocktails for a party without ruining them",
    "Simple syrup vs. gum syrup vs. sugar cube — which and when",
    "Overpouring vermouth in your Martini is killing it",
    "The dirty Martini debate — settled",
    "Citrus juice on ice — how long you actually have",
    "Rye vs. bourbon — pick the right whiskey for the drink",
    "The gin that punches above its price",
    "Coffee cocktails that aren't Espresso Martinis",
    "How to make a rich Sazerac at home",
    "Mezcal for Margarita beginners",
    "The Paper Plane recipe every home bar should know",
    "Why your Mojito is muddy — and the fix",
    "Fancy syrups from your pantry in 5 minutes",
    "Vodka is not boring — you're just picking wrong",
    "Sherry cocktails: the sleeper hit of a home bar",
    "How to stir vs. shake — the actual rule",
    "The Boulevardier is a better Negroni",
    "Amaro for beginners — three bottles, ten drinks",
    "The Corpse Reviver No. 2 belongs on every menu",
    "Rum: dark, gold, white — what actually matters",
    "The perfect Gin Martini — cold, dry, and simple",
    "Fresh lime or bottled — the honest answer",
    "How to hand-cut clear ice at home",
    "Milk-punch clarification without the fuss",
    "Cocktails for people who hate cocktails",
    "The one blender drink worth making",
    "Champagne cocktails that don't waste champagne",
    "Rickeys, fizzes and highballs — the summer trio",
    "The tiki drink that's easier than you think",
    "How to stock a bar cart for six good cocktails",
    "The Vieux Carré is the Manhattan you've been missing",
    "Rye Manhattan vs. bourbon Manhattan — pick a side",
    "The Gin Gimlet nobody makes right",
    "Tequila by category — blanco, reposado, añejo, choose fast",
    "Cachaça and the Caipirinha — the Brazilian rules",
    "How to build a signature drink from scratch",
    "The five bottles that make thirty drinks",
    "Pisco Sour — the underrated South American classic",
    "Cocktail cherries: Luxardo vs. everything else",
    "How salt fixes a broken cocktail",
    "The dive bar Old Fashioned — a love letter",
    "The Ramos Gin Fizz — 12 minutes of shaking, or?",
    "Sake cocktails you actually want to drink",
    "The clarified Milk Punch that ages for months",
]


async def next_topic(db: AsyncIOMotorDatabase) -> str:
    # User-added topics first (they're the freshest / most on-trend)
    user_topics = [
        d["topic"] async for d in db.autopilot_topics.find({}, {"_id": 0, "topic": 1}).sort("created_at", 1)
    ]
    effective = user_topics + SEED_TOPICS

    state = await db.autopilot_state.find_one({"_id": "primary"}) or {}
    cursor = int(state.get("cursor", 0)) % len(effective)
    topic = effective[cursor]

    await db.autopilot_state.update_one(
        {"_id": "primary"},
        {"$set": {"cursor": (cursor + 1) % len(effective), "last_topic": topic}},
        upsert=True,
    )
    return topic


async def add_user_topic(db: AsyncIOMotorDatabase, topic: str, created_at: str) -> None:
    await db.autopilot_topics.insert_one({"topic": topic.strip(), "created_at": created_at})


async def list_user_topics(db: AsyncIOMotorDatabase) -> list[dict]:
    return await db.autopilot_topics.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)


async def remove_user_topic(db: AsyncIOMotorDatabase, topic: str) -> int:
    r = await db.autopilot_topics.delete_one({"topic": topic})
    return r.deleted_count
