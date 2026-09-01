import httpx

from app.core.config import settings
from app.core.flow_log import flow_log

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
    if not settings.llm_api_key:
        key_name = "OPENROUTER_API_KEY" if settings.openrouter_enabled else "GROQ_API_KEY"
        raise RuntimeError(f"{key_name} is not set. Add it to backend/.env")

    context = build_context_block(matches)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"

    flow_log(
        "llm.request.started",
        model=settings.llm_model,
        provider=settings.llm_provider,
        question=question,
        source_count=len(matches),
        sources=[
            {
                "id": match.get("id"),
                "filename": match.get("filename"),
                "page": match.get("page"),
                "score": match.get("score"),
                "text": match.get("text"),
            }
            for match in matches
        ],
        context=context,
    )

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(settings.llm_url, json=payload, headers=headers)
        flow_log(
            "llm.response.received",
            model=settings.llm_model,
            provider=settings.llm_provider,
            status_code=resp.status_code,
            response_headers={
                key: value
                for key, value in resp.headers.items()
                if key.lower() not in {"authorization", "set-cookie"}
            },
            response_body=resp.text,
        )
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices")
    if not choices:
        # Some providers return 200 with an error body for failure modes
        # (e.g. model unavailable, no credit), so raise_for_status() alone
        # doesn't catch it.
        error = data.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(
            f"{settings.llm_provider} returned no choices: {message or data}"
        )

    answer = choices[0]["message"]["content"]
    flow_log(
        "llm.answer.extracted",
        model=settings.llm_model,
        provider=settings.llm_provider,
        answer=answer,
    )
    return answer
