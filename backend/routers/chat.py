"""Chat endpoints — web channel."""
from fastapi import APIRouter

from core.brain import chat_with_russell
from core.db import db
from core.models import ChatRequest, ChatResponse, now_iso

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    reply, actions = await chat_with_russell(req.session_id, req.message, channel="web")
    return ChatResponse(
        session_id=req.session_id,
        user_message=req.message,
        reply=reply,
        timestamp=now_iso(),
        actions=actions,
    )


@router.get("/chat/history")
async def chat_history(session_id: str = "main", limit: int = 100):
    msgs = await db.chat_messages.find(
        {"session_id": session_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(limit)
    return msgs


@router.delete("/chat/history")
async def clear_chat(session_id: str = "main"):
    result = await db.chat_messages.delete_many({"session_id": session_id})
    return {"deleted": result.deleted_count}
