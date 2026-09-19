"""Smoke test for LangGraph Agentic RAG integration."""

import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.agents.rag_graph import graph_rag
from app.services.retrieval import retriever
from app.core.config import settings

async def main():
    print("=== 1. Testing Retriever Initialization ===")
    retriever.ensure_bm25_index()
    print("BM25 index ready.")

    print("\n=== 2. Running Query Through LangGraph Agentic Pipeline ===")
    test_question = "What does `BILL-RESTOCK` mean?"
    print(f"Question: {test_question}")

    result = await graph_rag.run_rag_graph(
        question=test_question,
        top_k=3,
        hybrid=True,
        rerank=True,
    )

    print("\n--- Output Verification ---")
    print(f"Answer:\n{result['answer']}\n")
    print(f"Retrieved Chunks ({len(result['chunks'])}):")
    for c in result['chunks']:
        print(f"  - [{c.get('filename')} p.{c.get('page')}] Score: {c.get('score')} | ID: {c.get('id')}")

    trace = result["trace"]
    print("\n--- Trace Verification ---")
    print(f"Engine: {trace.get('engine')}")
    print(f"Agentic Info: {trace.get('agentic')}")
    print(f"Stages Executed ({len(trace.get('stages', []))}):")
    for s in trace.get("stages", []):
        print(f"  * {s.get('stage')} (took {s.get('timings_ms', 'N/A')}ms)")

    print(f"\nTimings Breakdown: {trace.get('timings_ms')}")
    print("\n>>> SMOKE TEST PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(main())
