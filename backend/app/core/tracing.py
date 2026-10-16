"""Lightweight span tracing for the multi-agent graph.

One *run* per user question, made of nested *spans* (agent node -> LLM call /
tool call). Context propagates through contextvars, so spans opened inside
asyncio.gather branches or LangGraph node tasks still attach to the right
parent without threading ids through every function signature.

    run = start_run()
    with span("manager", kind="agent") as s:
        s.set(use_live_data=True)

Spans are plain dicts so they serialise straight into the trace JSON.
"""

import functools
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional

MAX_ATTR_CHARS = 500
MAX_EVENTS_PER_SPAN = 50


class Run:
    def __init__(self, trace_id: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        self.trace_id = trace_id or f"tr_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.started = time.perf_counter()
        self.spans: List[Dict[str, Any]] = []


_run: ContextVar[Optional[Run]] = ContextVar("trace_run", default=None)
_current_span: ContextVar[Optional[Dict[str, Any]]] = ContextVar("trace_span", default=None)


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_ATTR_CHARS:
        return value[:MAX_ATTR_CHARS] + f"...[+{len(value) - MAX_ATTR_CHARS} chars]"
    return value


def _ms_since(run: Run) -> float:
    return round((time.perf_counter() - run.started) * 1000, 1)


def start_run(trace_id: Optional[str] = None) -> tuple[Run, Token]:
    run = Run(trace_id)
    return run, _run.set(run)


def end_run(token: Token) -> None:
    _run.reset(token)


def current_trace_id() -> Optional[str]:
    run = _run.get()
    return run.trace_id if run else None


def current_span_name() -> Optional[str]:
    span_ = _current_span.get()
    return span_["name"] if span_ else None


def add_event(name: str) -> None:
    """Attach a point-in-time marker (e.g. a flow_log event) to the open span."""
    run, span_ = _run.get(), _current_span.get()
    if run is None or span_ is None or len(span_["events"]) >= MAX_EVENTS_PER_SPAN:
        return
    span_["events"].append({"name": name, "at_ms": _ms_since(run)})


class _SpanHandle:
    def __init__(self, record: Optional[Dict[str, Any]]) -> None:
        self._record = record

    def set(self, **attrs: Any) -> None:
        if self._record is not None:
            self._record["attrs"].update({k: _clip(v) for k, v in attrs.items()})


@contextmanager
def span(name: str, kind: str = "internal", **attrs: Any) -> Iterator[_SpanHandle]:
    """Record a timed span. No-op (still yields a handle) outside a run."""
    run = _run.get()
    if run is None:
        yield _SpanHandle(None)
        return

    parent = _current_span.get()
    record: Dict[str, Any] = {
        "span_id": uuid.uuid4().hex[:8],
        "parent_id": parent["span_id"] if parent else None,
        "name": name,
        "kind": kind,
        "start_ms": _ms_since(run),
        "duration_ms": None,
        "status": "ok",
        "attrs": {k: _clip(v) for k, v in attrs.items()},
        "events": [],
    }
    run.spans.append(record)
    token = _current_span.set(record)
    started = time.perf_counter()
    try:
        yield _SpanHandle(record)
    except BaseException as error:
        record["status"] = "error"
        record["error"] = _clip(f"{type(error).__name__}: {error}")
        raise
    finally:
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        _current_span.reset(token)


def traced_node(name: str, kind: str = "agent") -> Callable:
    """Wrap a LangGraph node so its execution is one span."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: Dict[str, Any]) -> Dict[str, Any]:
            with span(name, kind=kind) as s:
                result = await fn(state)
                stage = next(
                    (st for st in reversed(state["trace"].get("stages", [])) if st.get("stage") == name),
                    None,
                )
                if stage:
                    s.set(**{k: v for k, v in stage.items() if isinstance(v, (str, int, float, bool))})
                return result

        return wrapper

    return decorator


def render_tree(spans: List[Dict[str, Any]]) -> str:
    """Indented, human-readable view of a run for console logs."""
    children: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for s in spans:
        children.setdefault(s["parent_id"], []).append(s)

    lines: List[str] = []

    def walk(parent_id: Optional[str], depth: int) -> None:
        for s in children.get(parent_id, []):
            flag = "" if s["status"] == "ok" else f"  !! {s.get('error', 'error')}"
            lines.append(f"{'  ' * depth}- [{s['kind']}] {s['name']}  {s['duration_ms']}ms{flag}")
            walk(s["span_id"], depth + 1)

    walk(None, 0)
    return "\n".join(lines)
