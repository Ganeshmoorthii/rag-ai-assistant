"""Console logging helpers for tracing one question through the pipeline."""

import json
from typing import Any


def flow_log(event: str, **data: Any) -> None:
    """Print structured question-flow data without exposing credentials."""
    payload = json.dumps(data, ensure_ascii=True, default=str)
    print(f"[QUESTION FLOW] {event} {payload}", flush=True)
