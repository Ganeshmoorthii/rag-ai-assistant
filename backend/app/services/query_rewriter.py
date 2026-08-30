"""Query rewriting and HyDE — fixing the question before you search.

THE PROBLEM
-----------
Users do not type search queries. They type things like:

    "hey so the thing where the rep gets money taken off, how much is it"

Nothing in that sentence lexically or semantically matches the chunk that
actually answers it ("commission is deducted from the rep (Item Cost x 1.4)").
The retrieval is not broken -- the *query* is broken. No amount of
reranking helps, because the correct chunk never enters the candidate list.

TWO FIXES, BOTH IMPLEMENTED HERE
--------------------------------
1. REWRITE (`rewrite_query`)
   Ask an LLM to restate the question as a dense, keyword-rich search query,
   preserving any exact identifiers verbatim. The example above becomes
   something like "rep commission deduction amount item cost multiplier".
   Cheap, predictable, and it keeps exact codes intact -- which matters
   because those codes are what BM25 keys on.

2. HyDE (`generate_hyde_document`) -- Hypothetical Document Embeddings
   A different trick with a neat insight: instead of making the question
   look more like a query, make it look like an ANSWER. Ask the LLM to
   *invent* a passage that would answer the question, then embed THAT and
   search with it.

   Why this works: you are searching a corpus of answer-shaped documents.
   A question and its answer are often lexically dissimilar ("how much is
   deducted?" vs "commission is deducted at Item Cost x 1.4"), so
   question->document similarity is a mismatch of registers.
   Document->document similarity is not. The hypothetical answer can be
   factually WRONG and still work, because it is only ever used as a
   retrieval probe -- it lands in the right neighbourhood of vector space
   and is then discarded. The real answer comes from the retrieved chunks.

COST
----
Both add one LLM call before retrieval: more latency, more spend. That is
the trade you are measuring.
"""

import re

import httpx

from app.core.config import settings
from app.core.flow_log import flow_log

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

REWRITE_SYSTEM = (
    "You rewrite user questions into concise search queries for a document "
    "retrieval system. Rules:\n"
    "- Keep every exact identifier verbatim: error codes, order types, "
    "field names, endpoints, serial numbers, file paths, ALL_CAPS terms.\n"
    "- Expand vague references into the concrete domain terms implied.\n"
    "- Strip conversational filler and politeness.\n"
    "- Reply with at most 15 words, on a single line.\n"
    "- Output ONLY the rewritten query. No preamble, no reasoning, no "
    "quotes, no explanation, no bullet points."
)

HYDE_SYSTEM = (
    "You write a short hypothetical passage that would plausibly answer the "
    "user's question, in the style of internal technical documentation. "
    "Two to three sentences. Use the specific vocabulary the real document "
    "would use. Do not hedge, do not say you are unsure, do not mention "
    "that this is hypothetical. Output only the passage."
)


async def _call_llm(system: str, user: str, max_tokens: int) -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to backend/.env")

    model = settings.rewrite_model.strip() or settings.openrouter_model
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        # Deterministic: the same question must rewrite the same way every
        # run, or your before/after numbers are measuring sampling noise.
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        flow_log(
            "query_transform.llm_response",
            model=payload["model"],
            status_code=resp.status_code,
            response_body=resp.text,
        )
        resp.raise_for_status()
        data = resp.json()

    return (data["choices"][0]["message"]["content"] or "").strip()


def _clean_rewrite(raw: str, question: str) -> str:
    """Strip reasoning-model chatter down to a usable search query.

    WHY THIS IS NEEDED (a real bug found while evaluating)
    ------------------------------------------------------
    Reasoning models (and many "free" OpenRouter models) ignore
    "output only the query" and emit their thinking first:

        'The user is asking about "the thing where the rep gets money
         taken off" - this sounds like a commission deduction...'

    Embedding THAT instead of a query is catastrophic: the probe is now
    mostly meta-commentary about the question, so dense search lands in
    completely the wrong region of vector space. In the first eval run
    this dropped hit-rate@3 from 88% to 84% -- query rewriting appeared
    to "not work" when in fact the rewriter output was never a query.

    Lesson worth keeping: when a technique underperforms, look at its
    actual intermediate output before concluding the technique is wrong.
    """
    if not raw:
        return question

    text = raw.strip()

    # Drop <think>...</think> blocks emitted by reasoning models.
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<thinking>.*?</thinking>", " ", text, flags=re.S | re.I)

    # Prefer an explicitly labelled query line if the model provided one.
    labelled = re.search(
        r"(?:rewritten query|search query|query)\s*[:\-]\s*(.+)", text, re.I
    )
    if labelled:
        text = labelled.group(1)

    # Otherwise take the last non-empty line: models that "think out loud"
    # nearly always put the actual deliverable last.
    lines = [ln.strip(" \t\"'`*-") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return question
    candidate = lines[-1]

    # Reject anything that still looks like prose about the question rather
    # than a query, and fall back to the user's own words -- which are at
    # least guaranteed to be on-topic.
    tells = (
        "the user is asking",
        "the user wants",
        "this sounds like",
        "i need to",
        "i should",
        "let me",
        "could refer to",
        "most likely",
        "i'll rewrite",
        "here is",
        "here's",
        "rewritten",
    )
    low = candidate.lower()
    if any(t in low for t in tells) or len(candidate.split()) > 25:
        return question

    # A response that got cut off by max_tokens often ends mid-sentence in a
    # colon or comma. Too short to be a real query -> fall back.
    if candidate.endswith((":", ",")) or len(candidate.split()) < 2:
        return question

    return candidate or question


async def rewrite_query(question: str) -> str:
    """Return a search-optimised version of `question`.

    Falls back to the original question on any failure -- a rewriter outage
    should degrade retrieval quality, never break the request.
    """
    try:
        raw = await _call_llm(REWRITE_SYSTEM, question, max_tokens=300)
        cleaned = _clean_rewrite(raw, question)
        flow_log("query_transform.rewrite_completed", raw=raw, cleaned=cleaned)
        return cleaned
    except Exception:  # noqa: BLE001 - deliberate graceful degradation
        flow_log("query_transform.rewrite_failed", question=question)
        return question


async def generate_hyde_document(question: str) -> str:
    """Return a hypothetical answer passage to use as the retrieval probe."""
    try:
        doc = await _call_llm(HYDE_SYSTEM, question, max_tokens=200)
        # Append the original question so exact identifiers from the user
        # survive into the probe even if the LLM paraphrased them away.
        result = f"{doc}\n\n{question}" if doc else question
        flow_log("query_transform.hyde_completed", raw=doc, result=result)
        return result
    except Exception:  # noqa: BLE001
        flow_log("query_transform.hyde_failed", question=question)
        return question
