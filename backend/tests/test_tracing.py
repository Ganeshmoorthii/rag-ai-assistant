"""Offline tests for multi-agent span tracing (no LLM / network needed)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import tracing


def test_spans_nest_and_survive_gather():
    async def branch(name):
        with tracing.span(f"branch.{name}", kind="retrieval"):
            await asyncio.sleep(0)
            with tracing.span("inner"):
                pass

    async def main():
        run, token = tracing.start_run()
        with tracing.span("root", kind="run"):
            await asyncio.gather(branch("a"), branch("b"))
        tracing.end_run(token)
        return run

    run = asyncio.run(main())
    by_name = {}
    for s in run.spans:
        by_name.setdefault(s["name"], []).append(s)
    root = by_name["root"][0]
    assert {s["parent_id"] for s in by_name["branch.a"] + by_name["branch.b"]} == {root["span_id"]}
    branch_ids = {s["span_id"] for s in by_name["branch.a"] + by_name["branch.b"]}
    assert {s["parent_id"] for s in by_name["inner"]} == branch_ids
    assert all(s["duration_ms"] is not None for s in run.spans)


def test_error_is_recorded_and_span_outside_run_is_noop():
    with tracing.span("no-run") as s:  # must not raise
        s.set(x=1)

    run, token = tracing.start_run()
    try:
        with tracing.span("boom"):
            raise ValueError("bad")
    except ValueError:
        pass
    tracing.end_run(token)
    assert run.spans[0]["status"] == "error"
    assert "ValueError: bad" in run.spans[0]["error"]


def test_full_graph_emits_spans_and_trace_id(monkeypatch, tmp_path):
    from app.services.agents.rag_graph import graph_rag, retrieval_agent
    from app.services.observability import trace_logger

    async def fake_llm(system_prompt, user_prompt, **kwargs):
        with tracing.span("llm.call", kind="llm"):
            if "operational database" in system_prompt:
                return '{"use_live_data": false, "reason": "docs only"}'
            if "Classify" in system_prompt:
                return '{"intent": "factual_lookup"}'
            return "answer"

    async def fake_retrieve(**kwargs):
        return {"chunks": [{"id": "c1", "filename": "a.pdf", "page": 1, "text": "t", "score": 0.9}]}

    monkeypatch.setattr(graph_rag.manager_agent.llm_client, "call_llm_text", fake_llm)
    monkeypatch.setattr(retrieval_agent.retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(retrieval_agent.settings, "grade_documents", False)
    monkeypatch.setattr(trace_logger.settings, "traces_path", str(tmp_path / "traces.jsonl"))

    async def no_tools(*a, **k):
        return [], {}

    monkeypatch.setattr(graph_rag.response_agent, "load_mcp_tools", no_tools)

    result = asyncio.run(graph_rag.run_rag_graph("What is X?"))
    trace = result["trace"]
    names = [s["name"] for s in trace["spans"]]
    for expected in ("rag_graph", "manager", "query_analyser", "retrieval_agent", "response_agent", "grade_generation"):
        assert expected in names
    assert trace["trace_id"].startswith("tr_")
    root = next(s for s in trace["spans"] if s["name"] == "rag_graph")
    nodes = [s for s in trace["spans"] if s["kind"] in ("agent", "check")]
    assert all(s["parent_id"] == root["span_id"] for s in nodes)
