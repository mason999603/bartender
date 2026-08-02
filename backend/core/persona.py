"""Russell's on-camera persona — one consistent Aussie bartender face across every daily video.

The persona is defined once as a detailed character sheet stored in Mongo
(`db.autopilot_persona`, `_id="primary"`). A reference PNG is rendered from
that sheet via GPT-Image-1 and cached on disk at
`/app/backend/generated/studio/persona.png`. Every Sora hero clip generated
by autopilot passes this image as `image_path`, so the same character
appears in every clip.

Regenerate the reference at any time via `POST /api/autopilot/persona/regenerate`.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import EMERGENT_LLM_KEY

logger = logging.getLogger("russell.persona")

# Same media dir as studio.py — reference image sits alongside generated clips
MEDIA_DIR = Path(os.environ.get("STUDIO_MEDIA_DIR", "/app/backend/generated/studio"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
PERSONA_IMAGE = MEDIA_DIR / "persona.png"

# The locked-in first-pass persona (user picked option a).
# This is the *character sheet* — a description dense enough that GPT-Image-1
# renders it consistently AND Sora can preserve it via the reference image.
DEFAULT_PERSONA = {
    "id": "russell-v1",
    "name": "Russell",
    "sheet": (
        "Photorealistic portrait of Russell, a rugged Australian bartender in his mid-30s. "
        "Sun-worn tanned skin, short dark brown hair with a slight wave, three-day stubble, "
        "warm brown eyes, calm confident half-smile. Full dark tattoo sleeve on the right arm "
        "showing traditional black-work Australian botanical designs. Wearing a fitted black henley "
        "with sleeves pushed up to the elbow, dark grey linen bar apron with brass eyelets. "
        "Standing behind a walnut bar counter with brass edging in a moody amber-lit speakeasy. "
        "Backlit by warm tungsten bulbs, hero light on the face from a small edison lamp above the bar. "
        "Shallow depth of field, cinematic 50mm lens, warm colour grade, subtle film grain, "
        "no logos, no text, no other people, no words in the image."
    ),
    # Shorter prompt fragment injected into Sora prompts so every clip is 'the same guy'
    "sora_snippet": (
        "The same rugged Australian bartender from the reference image — mid-30s, tanned skin, "
        "dark hair, three-day stubble, black henley with sleeves rolled up, dark grey apron, "
        "tattoo sleeve on right arm, in a moody amber-lit speakeasy behind a walnut bar."
    ),
}


async def load_persona(db: AsyncIOMotorDatabase) -> dict:
    doc = await db.autopilot_persona.find_one({"_id": "primary"}, {"_id": 0})
    return doc or DEFAULT_PERSONA


async def save_persona(db: AsyncIOMotorDatabase, persona: dict) -> None:
    doc = {"_id": "primary", **persona}
    await db.autopilot_persona.replace_one({"_id": "primary"}, doc, upsert=True)


def persona_image_exists() -> bool:
    return PERSONA_IMAGE.exists() and PERSONA_IMAGE.stat().st_size > 1000


async def ensure_persona_image(db: AsyncIOMotorDatabase, force: bool = False) -> Path:
    """Render (or return cached) persona reference PNG. Blocks up to ~30s on first call."""
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY not configured — needed to render persona")
    if not force and persona_image_exists():
        return PERSONA_IMAGE

    persona = await load_persona(db)
    # Keep the prompt focused on look, not action — the same character sheet, cleanly lit.
    prompt = persona["sheet"] + " Hero portrait, waist-up, looking slightly off camera, cinematic still."

    client = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
    images = await client.generate_images(
        prompt=prompt, model="gpt-image-1", number_of_images=1, quality="medium"
    )
    if not images:
        raise RuntimeError("GPT-Image-1 returned no image for persona render")
    PERSONA_IMAGE.write_bytes(images[0])
    logger.info("Persona image rendered → %s (%d bytes)", PERSONA_IMAGE, len(images[0]))
    return PERSONA_IMAGE


def persona_sora_snippet(persona: dict) -> str:
    """Fragment prepended to every autopilot Sora prompt so the character stays consistent."""
    return persona.get("sora_snippet") or DEFAULT_PERSONA["sora_snippet"]
