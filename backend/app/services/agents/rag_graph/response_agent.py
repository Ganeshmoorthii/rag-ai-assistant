"""Response Agent.

Converts retrieved evidence into a grounded and user-friendly response.

- Evidence Synthesis     -- combine relevant evidence from multiple chunks
  and sub-queries into one coherent answer, without unsupported claims.
- Answer Format Selection -- choose paragraph / bullets / numbered steps /
  table / summary based on the query_analyser's classified intent.
- Uncertainty Handling   -- when evidence is incomplete, conflicting, or
  insufficient (per the retrieval_agent's scoring), say so plainly instead
  of generating an unsupported answer.
"""

import re
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.llm import llm_client

FORMAT_BY_INTENT = {
    "factual_lookup": "a short, direct paragraph",
    "comparison": "a comparison table with one row per point of comparison",
    "summarization": "a concise set of bullet points",
    "troubleshooting": "numbered step-by-step instructions",
    "explanation": "a clear, multi-paragraph explanation",
}


def select_format(intent: str) -> str:
    """Answer format selection based on the query's classified intent."""
    return FORMAT_BY_INTENT.get(intent, FORMAT_BY_INTENT["factual_lookup"])


def build_system_prompt(format_instruction: str, uncertainty_note: Optional[str]) -> str:
    prompt = (
        "You are a helpful assistant answering questions using only the "
        "provided context from the user's documents. Combine evidence from "
        "every relevant passage into one coherent answer, and never state a "
        "claim the context does not support. Cite the filename and page "
        "number when relevant.\n\n"
        f"Format the answer as {format_instruction}."
    )
    if uncertainty_note:
        prompt += (
            "\n\nThe retrieved evidence has a gap: "
            f"{uncertainty_note}. Acknowledge this limitation plainly in "
            "the answer instead of filling the gap with unsupported claims."
        )
    return prompt


def _uncertainty_note(sufficient: bool, sub_results: List[Dict[str, Any]]) -> Optional[str]:
    """Summarize which sub-queries the retrieval_agent could not satisfy."""
    if sufficient:
        return None
    notes = []
    for sr in sub_results:
        if not sr.get("sufficient"):
            scores = sr.get("scores", {})
            reason = scores.get("reason") or "insufficient evidence coverage"
            notes.append(f'"{sr.get("sub_query", "")}" -- {reason}')
    if not notes:
        return None
    return "; ".join(notes)


async def synthesize_answer(
    question: str,
    documents: List[Dict[str, Any]],
    intent: str,
    sufficient: bool,
    sub_results: List[Dict[str, Any]],
    retrieval_only: bool = False,
) -> Dict[str, Any]:
    """Evidence synthesis + format selection + uncertainty handling."""
    t0 = time.perf_counter()

    format_instruction = select_format(intent)
    uncertainty_note = _uncertainty_note(sufficient, sub_results)

    if retrieval_only:
        answer = "(retrieval_only=true — generation skipped)"
    elif not documents:
        answer = "No relevant documents were found in the knowledge base to answer your question."
    else:
        system_prompt = build_system_prompt(format_instruction, uncertainty_note)
        context = llm_client.build_context_block(documents)
        user_content = f"Context:\n{context}\n\nQuestion: {question}"
        answer = await llm_client.call_llm_text(
            system_prompt=system_prompt,
            user_prompt=user_content,
            max_tokens=700,
            temperature=0.0,
        )

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    flow_log(
        "response_agent.synthesized",
        intent=intent,
        format=format_instruction,
        uncertainty_note=uncertainty_note,
        document_count=len(documents),
        elapsed_ms=elapsed,
    )
    return {
        "answer": answer,
        "format": format_instruction,
        "uncertainty_note": uncertainty_note,
        "elapsed_ms": elapsed,
    }


def grade_generation(answer: str, documents: List[Dict[str, Any]], retrieval_only: bool) -> str:
    """Groundedness check: do the answer's citations match retrieved chunks."""
    if retrieval_only:
        return "skipped_retrieval_only"
    if not documents or not settings.grade_hallucinations or not settings.llm_api_key:
        return "unverified"

    citations = re.findall(r"\[([^\]]+\.pdf)\s+p\.(\d+)\]", answer)
    if citations:
        known_pairs = {(d.get("filename"), str(d.get("page"))) for d in documents}
        grounded = all((f, p) in known_pairs for f, p in citations)
        return "grounded" if grounded else "citation_mismatch"
    return "grounded_no_citations"


# --- LangGraph nodes ---------------------------------------------------------

async def response_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapper: synthesize the final answer."""
    question = state["question"]
    documents = state.get("documents", [])
    intent = state.get("intent", "factual_lookup")
    sufficient = state.get("evidence_sufficient", True)
    sub_results = state.get("sub_results", [])
    cfg = state.get("config", {})
    trace = state["trace"]

    result = await synthesize_answer(
        question=question,
        documents=documents,
        intent=intent,
        sufficient=sufficient,
        sub_results=sub_results,
        retrieval_only=bool(cfg.get("retrieval_only")),
    )

    trace["timings_ms"]["response_agent"] = result["elapsed_ms"]
    trace["stages"].append(
        {
            "stage": "response_agent",
            "format": result["format"],
            "uncertainty_note": result["uncertainty_note"],
            "document_count": len(documents),
            "timings_ms": result["elapsed_ms"],
        }
    )

    return {
        "answer": result["answer"],
        "format": result["format"],
        "uncertainty_note": result["uncertainty_note"],
        "trace": trace,
    }


async def grade_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapper: groundedness check on the final answer."""
    t0 = time.perf_counter()
    answer = state.get("answer", "")
    documents = state.get("documents", [])
    cfg = state.get("config", {})
    trace = state["trace"]

    grade = grade_generation(answer, documents, bool(cfg.get("retrieval_only")))

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"]["grade_generation"] = elapsed
    trace["stages"].append(
        {
            "stage": "grade_generation",
            "hallucination_grade": grade,
            "timings_ms": elapsed,
        }
    )

    flow_log("response_agent.grade_generation", grade=grade)
    return {"hallucination_grade": grade, "trace": trace}
