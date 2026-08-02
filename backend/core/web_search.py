"""Live web search via Perplexity Sonar.

Russell calls this whenever he needs current or factual info (news, prices,
sports, "today's…", "look up X"). Every reply is grounded in real search
results with citation URLs — no hallucination.

We use the `sonar` model (cheap, ~$0.001/query) with OpenAI-compatible API.
`sonar-pro` is available for harder queries but not enabled by default to
keep costs pinned low.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger("russell.web_search")

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "").strip()
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar").strip()
USE_PERPLEXITY = bool(PERPLEXITY_API_KEY)


async def web_search(query: str, recency: Optional[str] = None) -> dict:
    """Ask Perplexity's Sonar model. Returns {answer, citations, model}.

    `recency` — optional filter: 'hour' | 'day' | 'week' | 'month' | 'year'.
    Useful for news queries where stale results are worse than nothing.
    """
    if not USE_PERPLEXITY:
        raise RuntimeError("Perplexity not configured — set PERPLEXITY_API_KEY")

    client = AsyncOpenAI(
        api_key=PERPLEXITY_API_KEY,
        base_url="https://api.perplexity.ai",
        timeout=25.0,
        max_retries=1,
    )

    # Small system prompt keeps Russell's voice on top of the search result.
    system = (
        "You're helping Russell — a witty Australian AI bartender. Answer the user's "
        "question tightly using ONLY live web results. Plain text, no markdown, no "
        "headings. If you're confident, be concise. If sources disagree, say so. "
        "Never invent facts."
    )

    kwargs: dict = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        "temperature": 0.3,
    }
    # Recency filter via web_search_options — supported by sonar models.
    if recency in {"hour", "day", "week", "month", "year"}:
        kwargs["web_search_options"] = {"search_recency_filter": recency}

    resp = await client.chat.completions.create(**kwargs)

    answer = (resp.choices[0].message.content or "").strip()
    # Citations come back on the response object under `citations` (list of URLs).
    citations = getattr(resp, "citations", None) or []

    return {
        "answer": answer,
        "citations": list(citations)[:8],
        "model": PERPLEXITY_MODEL,
    }
