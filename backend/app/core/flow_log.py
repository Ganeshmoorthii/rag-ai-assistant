"""Console logging helpers for tracing one question through the pipeline."""

import json
from typing import Any

from app.core import tracing


def flow_log(event: str, **data: Any) -> None:
    """Print structured question-flow data without exposing credentials.

    Inside a traced run, each line is tagged with the run's trace_id and the
    open span so logs from concurrent requests can be grepped apart, and the
    event is also recorded on the span.
    """
    trace_id = tracing.current_trace_id()
    if trace_id:
        data = {"trace_id": trace_id, "span": tracing.current_span_name(), **data}
        tracing.add_event(event)
    payload = json.dumps(data, ensure_ascii=True, default=str)
    print(f"[QUESTION FLOW] {event} {payload}", flush=True)
