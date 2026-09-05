"""Trace logging service for persisting live user query interactions to JSONL.

Aligns with Week 5 schema audit and replayability requirements.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.llm_client import SYSTEM_PROMPT

_lock = threading.Lock()


def get_traces_file_path() -> str:
    """Resolve the absolute path to the traces file."""
    raw_path = settings.traces_path
    if os.path.isabs(raw_path):
        return raw_path

    # Check if relative to cwd
    if os.path.exists(raw_path) or os.path.exists(os.path.dirname(raw_path) or "."):
        return os.path.abspath(raw_path)

    # Fallback relative to backend root
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.abspath(os.path.join(backend_root, raw_path))


def log_interaction_trace(
    question: str,
    chunks: list[dict],
    answer: str,
    trace_info: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    model: str | None = None,
    model_params: dict[str, Any] | None = None,
    prompt_version: str = "v1.0.0",
    system_prompt: str = SYSTEM_PROMPT,
    trace_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    """Persist a live user interaction trace into traces.jsonl.

    Guarantees conformance with Week 5 schema audit and replayability requirements.
    """
    if not settings.trace_logging_enabled:
        return None

    try:
        now = datetime.now(timezone.utc)
        tid = trace_id or f"tr_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Format chunks to preserve schema
        retrieved_chunks = []
        for c in chunks or []:
            score = c.get("score")
            if score is None:
                score = c.get("rrf_score")
            if score is None:
                score = c.get("rerank_score")

            retrieved_chunks.append(
                {
                    "id": c.get("id"),
                    "filename": c.get("filename"),
                    "page": c.get("page"),
                    "score": round(float(score), 4) if score is not None else None,
                    "text": c.get("text", ""),
                }
            )

        t_info = trace_info or {}

        record = {
            "trace_id": tid,
            "timestamp": now.isoformat(),
            "original_question": question,
            "prompt_version": prompt_version,
            "system_prompt": system_prompt,
            "model": model or settings.llm_model,
            "model_params": model_params
            or {
                "temperature": 0.0,
                "max_tokens": 1024,
                "top_p": 1.0,
            },
            "config": config
            or {
                "top_k": settings.top_k,
                "hybrid": settings.hybrid_enabled,
                "rerank": settings.rerank_enabled,
                "rewrite": settings.rewrite_enabled,
                "mmr": settings.mmr_enabled,
            },
            "retrieved_chunks": retrieved_chunks,
            "raw_output": answer if error is None else f"Error: {error}",
            "answer": answer,
            "stages": t_info.get("stages", []),
            "timings_ms": t_info.get("timings_ms", {}),
        }
        if error:
            record["error"] = error

        file_path = get_traces_file_path()
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        flow_log("trace.logged", trace_id=tid, file=file_path)
        return record
    except Exception as e:
        flow_log("trace.log_error", error=str(e))
        return None
