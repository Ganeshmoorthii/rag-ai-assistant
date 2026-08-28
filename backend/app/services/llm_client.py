import httpx

from app.core.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions using only the provided "
    "context from the user's documents. If the answer isn't in the context, "
    "say you don't know. Cite the filename and page number when relevant."
)


def build_context_block(matches: list[dict]) -> str:
    parts = []
    for m in matches:
        parts.append(f"[{m['filename']} p.{m['page']}]\n{m['text']}")
    return "\n\n---\n\n".join(parts)


async def generate_answer(question: str, matches: list[dict]) -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to backend/.env")

    context = build_context_block(matches)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices")
    if not choices:
        # OpenRouter returns 200 with an error body for some failure modes
        # (e.g. model unavailable, no credit), so raise_for_status() alone
        # doesn't catch it.
        error = data.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(
            f"OpenRouter returned no choices: {message or data}"
        )

    return choices[0]["message"]["content"]
