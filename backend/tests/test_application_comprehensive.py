"""Comprehensive Test Suite for the RAG Assistant & LangGraph Pipeline.

Covers:
1. Ingestion & Document Processing (clean_text, chunk_text, table_to_markdown)
2. In-memory BM25 Keyword Search & Tokenization
3. Fusion & Ranking Algorithms (RRF, MMR)
4. Evaluation Metrics (hit@k, recall@k, MRR, aggregate)
5. LangGraph Agentic Pipeline Nodes & State Transitions
6. FastAPI API Endpoints (health, configs, triage, query linear vs graph)
"""

import asyncio
import os
import re
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.retrieval import bm25, metrics, retriever
from app.services.ingestion import chunker, pdf_loader
from app.services.agents.rag_graph import graph_rag


class TestDocumentProcessing(unittest.TestCase):
    """Test text cleaning, chunking, and markdown conversion."""

    def test_clean_text_artifacts(self):
        raw = "Error\ufffdcode ~— test INSTRUMENT-  QUOTE"
        cleaned = pdf_loader.clean_text(raw)
        self.assertNotIn("\ufffd", cleaned)
        self.assertIn("—", cleaned)
        self.assertIn("INSTRUMENT-QUOTE", cleaned)

    def test_table_to_markdown(self):
        rows = [
            ["Item", "Code", "Price"],
            ["Stent", "ST-101", "$500"],
            ["Catheter", "CT-202", "$150"],
        ]
        md = pdf_loader.table_to_markdown(rows)
        self.assertIn("| Item | Code | Price |", md)
        self.assertIn("| --- | --- | --- |", md)
        self.assertIn("| Stent | ST-101 | $500 |", md)

    def test_table_to_markdown_empty(self):
        self.assertEqual(pdf_loader.table_to_markdown([]), "")
        self.assertEqual(pdf_loader.table_to_markdown([["Single row"]]), "")

    def test_chunk_text_basic(self):
        text = "word " * 1500
        chunks = chunker.chunk_text(text, chunk_size=500, overlap=100)
        self.assertTrue(len(chunks) >= 3)
        for c in chunks:
            self.assertLessEqual(len(c.split()), 500)

    def test_chunk_text_empty(self):
        self.assertEqual(chunker.chunk_text(""), [])
        self.assertEqual(chunker.chunk_text("   "), [])


class TestBM25Index(unittest.TestCase):
    """Test lexical tokenization and BM25 index math."""

    def test_tokenize_preserves_code_identifiers(self):
        query = "What does BILL-RESTOCK and cim_auth_check with flag -L mean?"
        tokens = bm25.tokenize(query)
        self.assertIn("bill-restock", tokens)
        self.assertIn("restock", tokens)
        self.assertIn("bill", tokens)
        self.assertIn("cim_auth_check", tokens)
        self.assertIn("l", tokens)

    def test_bm25_search_scoring(self):
        test_index = bm25.BM25Index()
        records = [
            {
                "id": "doc_1",
                "text": "The BILL-RESTOCK order requires immediate warehouse fulfillment.",
                "filename": "orders.pdf",
                "page": 1,
                "doc_id": "d1",
            },
            {
                "id": "doc_2",
                "text": "Regular user authentication and login with OAuth2 JWT token.",
                "filename": "auth.pdf",
                "page": 1,
                "doc_id": "d2",
            },
            {
                "id": "doc_3",
                "text": "General inventory restocking procedure and warehouse shipping.",
                "filename": "inventory.pdf",
                "page": 2,
                "doc_id": "d3",
            },
        ]
        test_index.build(records)
        self.assertEqual(test_index.size, 3)

        # Exact query should rank doc_1 highest
        results = test_index.search("BILL-RESTOCK", top_k=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "doc_1")
        self.assertGreater(results[0]["score"], 0)


class TestRetrievalLogic(unittest.TestCase):
    """Test fusion (RRF) and MMR algorithms."""

    def test_reciprocal_rank_fusion(self):
        dense = [
            {"id": "c1", "score": 0.9, "text": "chunk 1"},
            {"id": "c2", "score": 0.8, "text": "chunk 2"},
            {"id": "c3", "score": 0.7, "text": "chunk 3"},
        ]
        sparse = [
            {"id": "c2", "score": 12.5, "text": "chunk 2"},
            {"id": "c4", "score": 10.0, "text": "chunk 4"},
            {"id": "c1", "score": 5.0, "text": "chunk 1"},
        ]
        fused = retriever.reciprocal_rank_fusion({"dense": dense, "sparse": sparse}, rrf_k=60)
        self.assertGreater(len(fused), 0)

        # c2 is rank 2 in dense and rank 1 in sparse -> highest agreement
        top_id = fused[0]["id"]
        self.assertEqual(top_id, "c2")

        # Provenance must be recorded
        self.assertIn("retrievers", fused[0])
        self.assertIn("dense", fused[0]["retrievers"])
        self.assertIn("sparse", fused[0]["retrievers"])
        self.assertEqual(fused[0]["retrievers"]["sparse"]["rank"], 1)

    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(retriever._cosine(v1, v2), 1.0)
        self.assertAlmostEqual(retriever._cosine(v1, v3), 0.0)


class TestEvaluationMetrics(unittest.TestCase):
    """Test hit@k, recall@k, and MRR metrics."""

    def setUp(self):
        self.expected = [{"filename": "Advita DOCs.pdf", "page": 2}]
        self.chunks_hit = [
            {"filename": "Advita DOCs.pdf", "page": 14, "score": 0.9},
            {"filename": "Advita DOCs.pdf", "page": 2, "score": 0.8},
            {"filename": "Advita DOCs.pdf", "page": 5, "score": 0.7},
        ]
        self.chunks_miss = [
            {"filename": "Advita DOCs.pdf", "page": 14, "score": 0.9},
            {"filename": "Advita DOCs.pdf", "page": 6, "score": 0.8},
            {"filename": "Advita DOCs.pdf", "page": 5, "score": 0.7},
        ]

    def test_hit_at_k(self):
        self.assertFalse(metrics.hit_at_k(self.chunks_hit, self.expected, k=1))
        self.assertTrue(metrics.hit_at_k(self.chunks_hit, self.expected, k=2))
        self.assertTrue(metrics.hit_at_k(self.chunks_hit, self.expected, k=3))
        self.assertFalse(metrics.hit_at_k(self.chunks_miss, self.expected, k=3))

    def test_recall_at_k(self):
        expected_multi = [
            {"filename": "Advita DOCs.pdf", "page": 2},
            {"filename": "Advita DOCs.pdf", "page": 5},
        ]
        self.assertAlmostEqual(metrics.recall_at_k(self.chunks_hit, expected_multi, k=1), 0.0)
        self.assertAlmostEqual(metrics.recall_at_k(self.chunks_hit, expected_multi, k=2), 0.5)
        self.assertAlmostEqual(metrics.recall_at_k(self.chunks_hit, expected_multi, k=3), 1.0)

    def test_first_hit_rank_and_mrr(self):
        self.assertEqual(metrics.first_hit_rank(self.chunks_hit, self.expected), 2)
        self.assertAlmostEqual(metrics.reciprocal_rank(self.chunks_hit, self.expected), 0.5)

        self.assertIsNone(metrics.first_hit_rank(self.chunks_miss, self.expected))
        self.assertEqual(metrics.reciprocal_rank(self.chunks_miss, self.expected), 0.0)

    def test_aggregate_summary(self):
        per_q = [
            {"chunks": self.chunks_hit, "expected": self.expected},
            {"chunks": self.chunks_miss, "expected": self.expected},
        ]
        agg = metrics.aggregate(per_q, [1, 3])
        self.assertEqual(agg["n"], 2)
        self.assertEqual(agg["hit_rate@1"], 0.0)
        self.assertEqual(agg["hit_rate@3"], 0.5)
        self.assertEqual(agg["mrr"], 0.25)


class TestLangGraphNodes(unittest.IsolatedAsyncioTestCase):
    """Test individual LangGraph Agentic nodes and state progression."""

    async def test_route_query_node_exact_identifier(self):
        state: graph_rag.RAGGraphState = {
            "question": "What is the return type of `getBackorders()` and code BILL-RESTOCK?",
            "search_query": "",
            "documents": [],
            "answer": "",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {},
        }
        res = await graph_rag.route_query_node(state)
        self.assertEqual(res["route"], "exact_identifier")
        self.assertEqual(len(state["trace"]["stages"]), 1)
        self.assertEqual(state["trace"]["stages"][0]["stage"], "graph_route")
        self.assertTrue(state["trace"]["stages"][0]["has_exact_identifier"])

    async def test_route_query_node_conceptual(self):
        state: graph_rag.RAGGraphState = {
            "question": "Can you give me a general overview of the product documentation?",
            "search_query": "",
            "documents": [],
            "answer": "",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {},
        }
        res = await graph_rag.route_query_node(state)
        self.assertEqual(res["route"], "semantic_concept")

    async def test_grade_documents_node_empty(self):
        state: graph_rag.RAGGraphState = {
            "question": "Nonexistent topic",
            "search_query": "Nonexistent topic",
            "documents": [],
            "answer": "",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "semantic_concept",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {},
        }
        res = await graph_rag.grade_documents_node(state)
        self.assertTrue(res["needs_rewrite"])
        self.assertEqual(res["document_grades"][0]["reason"], "empty")

    def test_decide_to_generate_conditional_edge(self):
        # Case 1: needs rewrite and retries remain -> rewrite_query
        state_retry = {"needs_rewrite": True, "retry_count": 0, "max_retries": 1}
        self.assertEqual(graph_rag.decide_to_generate(state_retry), "rewrite_query")

        # Case 2: needs rewrite but retries exhausted -> generate
        state_exhausted = {"needs_rewrite": True, "retry_count": 1, "max_retries": 1}
        self.assertEqual(graph_rag.decide_to_generate(state_exhausted), "generate")

        # Case 3: documents are relevant -> generate
        state_ok = {"needs_rewrite": False, "retry_count": 0, "max_retries": 1}
        self.assertEqual(graph_rag.decide_to_generate(state_ok), "generate")

    async def test_generate_node_retrieval_only(self):
        state: graph_rag.RAGGraphState = {
            "question": "What is BILL-RESTOCK?",
            "search_query": "What is BILL-RESTOCK?",
            "documents": [{"id": "c1", "text": "Some text", "filename": "doc.pdf", "page": 1}],
            "answer": "",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "semantic_concept",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {"retrieval_only": True},
        }
        res = await graph_rag.generate_node(state)
        self.assertIn("retrieval_only=true", res["answer"])

    async def test_grade_generation_node_citation_matching(self):
        docs = [{"filename": "Advita DOCs.pdf", "page": 14, "text": "sample"}]

        # Good citations
        state_good: graph_rag.RAGGraphState = {
            "question": "q",
            "search_query": "q",
            "documents": docs,
            "answer": "This is defined in [Advita DOCs.pdf p.14] explicitly.",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "semantic_concept",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {},
        }
        res_good = await graph_rag.grade_generation_node(state_good)
        self.assertEqual(res_good["hallucination_grade"], "grounded")

        # Hallucinated / Mismatched citation
        state_bad: graph_rag.RAGGraphState = {
            "question": "q",
            "search_query": "q",
            "documents": docs,
            "answer": "This is defined in [Nonexistent.pdf p.99] explicitly.",
            "retry_count": 0,
            "max_retries": 1,
            "needs_rewrite": False,
            "route": "semantic_concept",
            "document_grades": [],
            "hallucination_grade": None,
            "trace": {"stages": [], "timings_ms": {}},
            "config": {},
        }
        res_bad = await graph_rag.grade_generation_node(state_bad)
        self.assertEqual(res_bad["hallucination_grade"], "citation_mismatch")


class TestFastAPIEndpoints(unittest.IsolatedAsyncioTestCase):
    """Test full application HTTP API via ASGI Transport."""

    async def asyncSetUp(self):
        self.transport = ASGITransport(app=app)
        self.client = AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_health(self):
        resp = await self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    async def test_get_configs(self):
        resp = await self.client.get("/api/configs")
        self.assertEqual(resp.status_code, 200)
        configs = resp.json()
        names = [c["name"] for c in configs]
        self.assertIn("baseline", names)
        self.assertIn("hybrid", names)
        self.assertIn("rerank", names)
        self.assertIn("langgraph", names)

    async def test_get_golden_set(self):
        resp = await self.client.get("/api/golden-set")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("questions", data)
        self.assertGreater(len(data["questions"]), 0)

    async def test_get_retrieval_settings(self):
        resp = await self.client.get("/api/retrieval-settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("top_k", data)
        self.assertIn("bm25_index_size", data)

    async def test_post_query_linear_retrieval_only(self):
        payload = {
            "question": "What does BILL-RESTOCK mean?",
            "top_k": 2,
            "retrieval_only": True,
            "use_graph": False,
        }
        resp = await self.client.post("/api/query", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("answer", data)
        self.assertIn("retrieval_only=true", data["answer"])
        self.assertIn("sources", data)
        self.assertIn("trace", data)
        self.assertEqual(len(data["sources"]), 2)

    async def test_post_query_langgraph_retrieval_only(self):
        payload = {
            "question": "What does BILL-RESTOCK mean?",
            "top_k": 2,
            "retrieval_only": True,
            "use_graph": True,
        }
        resp = await self.client.post("/api/query", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("answer", data)
        self.assertIn("retrieval_only=true", data["answer"])
        self.assertIn("sources", data)
        self.assertIn("trace", data)
        self.assertEqual(data["trace"].get("engine"), "langgraph")
        self.assertIn("agentic", data["trace"])
        self.assertEqual(data["trace"]["agentic"]["route"], "exact_identifier")

    async def test_post_triage(self):
        payload = {
            "question": "What does BILL-RESTOCK mean?",
            "expected": [{"filename": "Advita DOCs.pdf", "page": 2}],
            "top_k": 3,
            "generate": False,
        }
        resp = await self.client.post("/api/triage", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("verdict", data)
        self.assertIn("reasoning", data)
        self.assertIn("hit_at_k", data)
        self.assertIn("recall_at_k", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
