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
        "max_tokens": 600,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    data = None
    for attempt in range(4):
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
            if resp.status_code == 429:
                raw_reset = resp.headers.get("x-ratelimit-reset-tokens", "")
                reset_s = 6.0
                import re
                m = re.search(r"([\d\.]+)", raw_reset)
                if m:
                    reset_s = float(m.group(1)) + 0.5
                import asyncio
                await asyncio.sleep(min(reset_s, 60.0))
                continue
            resp.raise_for_status()
            data = resp.json()
            break

    if data is None:
        raise RuntimeError("LLM request repeatedly rate-limited. Please retry shortly.")

    choices = data.get("choices")
    if not choices:
        error = data.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(
            f"{settings.llm_provider} returned no choices: {message or data}"
        )

    raw_content = choices[0]["message"]["content"]
    import re
    answer = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
    flow_log(
        "llm.answer.extracted",
        model=settings.llm_model,
        provider=settings.llm_provider,
        answer=answer,
    )
    return answer


async def call_llm_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.0,
) -> str:
    """Generic text completion helper used by LangGraph grading nodes."""
    if not settings.llm_api_key:
        key_name = "OPENROUTER_API_KEY" if settings.openrouter_enabled else "GROQ_API_KEY"
        raise RuntimeError(f"{key_name} is not set. Add it to backend/.env")

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    data = None
    for attempt in range(4):
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(settings.llm_url, json=payload, headers=headers)
            if resp.status_code == 429:
                raw_reset = resp.headers.get("x-ratelimit-reset-tokens", "")
                reset_s = 5.0
                import re
                m = re.search(r"([\d\.]+)", raw_reset)
                if m:
                    reset_s = float(m.group(1)) + 0.5
                import asyncio
                await asyncio.sleep(min(reset_s, 60.0))
                continue
            resp.raise_for_status()
            data = resp.json()
            break

    if data is None:
        raise RuntimeError("LLM text call repeatedly rate-limited. Please retry shortly.")

    choices = data.get("choices")
    if not choices:
        error = data.get("error", {})
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(
            f"{settings.llm_provider} returned no choices: {message or data}"
        )

    raw_text = choices[0]["message"]["content"]
    import re
    return re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
