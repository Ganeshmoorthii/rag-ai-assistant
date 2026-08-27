"""The retrieval pipeline — one place where every strategy is composed.

PIPELINE SHAPE
--------------
    question
      |
      +-- (optional) query rewrite / HyDE      <- fix a broken question
      |
      +-- dense search (embeddings)  --\
      |                                 >-- RRF fusion   <- fix missed
      +-- BM25 search (keywords)     --/                    exact terms
      |
      +-- (optional) cross-encoder rerank      <- fix bad ordering
      |
      +-- (optional) MMR diversity filter      <- fix duplicate chunks
      |
      v
    top_k chunks  +  a trace of every stage

Every stage is individually switchable from .env, and every stage records
what it did into a trace. The trace is what makes the difference between
"it feels better" and a number you can defend.
"""

import time

from app.core.config import settings
from app.services import bm25, reranker, vector_store


# --- BM25 index lifecycle -------------------------------------------------

def ensure_bm25_index(force: bool = False) -> int:
    """Build the BM25 index from ChromaDB if needed. Returns chunk count.

    The BM25 index lives in memory, so it must be rebuilt on process start
    and after any ingest/delete. Cheap for corpora of this size.
    """
    if force or not bm25.index.is_built():
        records = vector_store.get_all_chunks()
        bm25.index.build(records)
    return bm25.index.size


def invalidate_bm25_index() -> None:
    """Call after documents change so the next query rebuilds the index."""
    ensure_bm25_index(force=True)


# --- Reciprocal Rank Fusion ----------------------------------------------

def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[dict]], rrf_k: int | None = None
) -> list[dict]:
    """Fuse several ranked lists into one, using RRF.

    WHY RRF INSTEAD OF ADDING THE SCORES
    ------------------------------------
    Dense similarity is roughly 0..1. BM25 is unbounded and depends on
    corpus statistics -- a rare-term match can score 8, 15, whatever. The
    two numbers are not on a common scale, so `0.7*dense + 0.3*bm25` is
    meaningless: the weights would need retuning for every new corpus, and
    a single high-IDF term would swamp the dense signal.

    RRF throws the scores away and keeps only the RANKS:

        rrf_score(chunk) = sum over each retriever of  1 / (k + rank)

    Rank is scale-free, so no normalisation or tuning is needed. A chunk
    ranked 1st by BM25 and 1st by dense scores 2/(k+1) and wins. A chunk
    ranked 1st by one retriever and absent from the other still scores
    1/(k+1), which is how exact-term matches get rescued -- BM25 alone is
    enough to pull a chunk into the final top 3.

    k (default 60, from the original RRF paper) damps the curve. With k=60
    the gap between rank 1 and rank 2 is small, so agreement across
    retrievers matters more than being top of any single list. A small k
    would make rank 1 dominate and effectively reduce this to "whoever
    won one list wins".
    """
    rrf_k = rrf_k if rrf_k is not None else settings.rrf_k

    fused: dict[str, dict] = {}

    for source, ranked in ranked_lists.items():
        for rank, item in enumerate(ranked, start=1):
            cid = item["id"]
            contribution = 1.0 / (rrf_k + rank)

            if cid not in fused:
                fused[cid] = {
                    **{k: v for k, v in item.items() if k != "score"},
                    "rrf_score": 0.0,
                    # Per-retriever provenance: this is the evidence that
                    # tells you WHICH retriever found a chunk, which is the
                    # whole point of running a hybrid.
                    "retrievers": {},
                }
            fused[cid]["rrf_score"] += contribution
            fused[cid]["retrievers"][source] = {
                "rank": rank,
                "score": item.get("score"),
                "rrf_contribution": round(contribution, 6),
            }

    out = list(fused.values())
    out.sort(key=lambda c: -c["rrf_score"])
    for item in out:
        item["score"] = item["rrf_score"]
    return out


# --- MMR ------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def apply_mmr(
    question: str, candidates: list[dict], top_k: int, lambda_mult: float | None = None
) -> list[dict]:
    """Maximal Marginal Relevance — trade a little relevance for diversity.

    THE PROBLEM MMR SOLVES
    ----------------------
    Chunks overlap (you use a 150-word overlap), and documents repeat
    themselves. So the top 3 can easily be three near-copies of the same
    passage. You have technically retrieved 3 chunks and actually retrieved
    1 fact -- wasting two thirds of the context window and often missing
    the second fact a multi-part question needed.

    THE FORMULA
    -----------
    Pick greedily. At each step, choose the candidate maximising:

        lambda * relevance(c, query)
          - (1 - lambda) * max similarity(c, already_selected)

    So a chunk is penalised for resembling something already picked.

        lambda = 1.0  -> pure relevance (MMR off)
        lambda = 0.7  -> default: mostly relevance, break up duplicates
        lambda = 0.0  -> pure diversity (ignores the question entirely)

    NOTE: this can LOWER hit-rate@k, and that is not a bug. MMR optimises
    for covering distinct information, not for ranking one gold chunk top.
    If your eval questions each have exactly one correct chunk, expect MMR
    to look neutral or slightly negative -- it pays off on multi-fact
    questions, which a single-gold-chunk metric cannot see.
    """
    lambda_mult = (
        lambda_mult if lambda_mult is not None else settings.mmr_lambda
    )
    if not candidates or top_k <= 0:
        return []
    if len(candidates) <= 1:
        return candidates[:top_k]

    ids = [c["id"] for c in candidates]
    emb_map = vector_store.get_embeddings(ids)
    # If embeddings are unavailable, fail open: return the input order.
    if not emb_map:
        return candidates[:top_k]

    q_emb = vector_store.embed_query(question)

    # Relevance to the query, computed in embedding space so it is on the
    # same scale as the diversity penalty.
    rel: dict[str, float] = {}
    for cid in ids:
        emb = emb_map.get(cid)
        rel[cid] = _cosine(q_emb, emb) if emb else 0.0

    selected: list[dict] = []
    remaining = list(candidates)

    while remaining and len(selected) < top_k:
        best_item = None
        best_score = None

        for cand in remaining:
            cid = cand["id"]
            emb = emb_map.get(cid)

            if selected and emb:
                redundancy = max(
                    _cosine(emb, emb_map[s["id"]])
                    for s in selected
                    if s["id"] in emb_map
                )
            else:
                redundancy = 0.0

            mmr_score = lambda_mult * rel[cid] - (1 - lambda_mult) * redundancy

            if best_score is None or mmr_score > best_score:
                best_score = mmr_score
                best_item = cand

        item = dict(best_item)
        item["mmr_score"] = round(best_score, 6)
        item["mmr_relevance"] = round(rel[best_item["id"]], 6)
        selected.append(item)
        remaining.remove(best_item)

    return selected


# --- the pipeline ---------------------------------------------------------

async def retrieve(
    question: str,
    top_k: int | None = None,
    hybrid: bool | None = None,
    rerank: bool | None = None,
    rewrite: bool | None = None,
    mmr: bool | None = None,
    hyde: bool = False,
) -> dict:
    """Run the retrieval pipeline and return {chunks, trace}.

    Every flag defaults to its .env setting, but can be overridden per
    call -- which is what lets the eval harness measure one variable at a
    time against a single running index.
    """
    top_k = top_k or settings.top_k
    hybrid = settings.hybrid_enabled if hybrid is None else hybrid
    do_rerank = settings.rerank_enabled if rerank is None else rerank
    do_rewrite = settings.rewrite_enabled if rewrite is None else rewrite
    do_mmr = settings.mmr_enabled if mmr is None else mmr

    trace: dict = {
        "original_question": question,
        "config": {
            "top_k": top_k,
            "hybrid": hybrid,
            "rerank": do_rerank,
            "rewrite": do_rewrite,
            "hyde": hyde,
            "mmr": do_mmr,
            "candidate_k": settings.candidate_k,
            "rrf_k": settings.rrf_k,
        },
        "stages": [],
        "timings_ms": {},
    }

    # -- Stage 1: query transformation ------------------------------------
    search_query = question
    if do_rewrite or hyde:
        t0 = time.perf_counter()
        from app.services import query_rewriter

        if hyde:
            search_query = await query_rewriter.generate_hyde_document(question)
            method = "hyde"
        else:
            search_query = await query_rewriter.rewrite_query(question)
            method = "rewrite"

        trace["timings_ms"]["query_transform"] = round(
            (time.perf_counter() - t0) * 1000, 1
        )
        trace["search_query"] = search_query
        trace["stages"].append(
            {
                "stage": "query_transform",
                "method": method,
                "before": question,
                "after": search_query,
                "changed": search_query.strip() != question.strip(),
            }
        )
    else:
        trace["search_query"] = question

    # -- Stage 2: candidate retrieval --------------------------------------
    # Over-fetch when a later stage will re-order or filter: a reranker can
    # only promote a chunk that retrieval already found. `candidate_k` is
    # the ceiling on what the whole pipeline can possibly get right.
    needs_candidates = hybrid or do_rerank or do_mmr
    fetch_n = max(settings.candidate_k, top_k) if needs_candidates else top_k

    t0 = time.perf_counter()
    dense_results = vector_store.query(search_query, top_k=fetch_n)
    trace["timings_ms"]["dense_search"] = round((time.perf_counter() - t0) * 1000, 1)
    trace["stages"].append(
        {
            "stage": "dense_search",
            "query": search_query,
            "returned": len(dense_results),
            "top": _summarize(dense_results, 5),
        }
    )

    if hybrid:
        ensure_bm25_index()
        t0 = time.perf_counter()
        # BM25 searches with the ORIGINAL question, not the rewrite. The
        # rewrite is tuned for semantic search; the user's own wording is
        # where exact identifiers live, and paraphrasing can lose them.
        bm25_results = bm25.index.search(question, top_k=fetch_n)
        trace["timings_ms"]["bm25_search"] = round(
            (time.perf_counter() - t0) * 1000, 1
        )
        trace["stages"].append(
            {
                "stage": "bm25_search",
                "query": question,
                "query_terms": bm25.tokenize(question),
                "returned": len(bm25_results),
                "top": _summarize(bm25_results, 5),
            }
        )

        t0 = time.perf_counter()
        candidates = reciprocal_rank_fusion(
            {"dense": dense_results, "bm25": bm25_results}
        )
        trace["timings_ms"]["fusion"] = round((time.perf_counter() - t0) * 1000, 1)

        dense_ids = {c["id"] for c in dense_results[:top_k]}
        bm25_ids = {c["id"] for c in bm25_results[:top_k]}
        trace["stages"].append(
            {
                "stage": "rrf_fusion",
                "rrf_k": settings.rrf_k,
                "fused_count": len(candidates),
                # The money line for the writeup: chunks BM25 contributed
                # that dense search would have missed entirely.
                "bm25_only_in_top_k": sorted(bm25_ids - dense_ids),
                "dense_only_in_top_k": sorted(dense_ids - bm25_ids),
                "agreed_in_top_k": sorted(dense_ids & bm25_ids),
                "top": _summarize(candidates, 5),
            }
        )
    else:
        candidates = dense_results

    retrieval_order = [c["id"] for c in candidates[:top_k]]

    # -- Stage 3: reranking ------------------------------------------------
    if do_rerank and candidates:
        t0 = time.perf_counter()
        try:
            pool = candidates[: settings.rerank_candidates]
            reranked = reranker.rerank(question, pool, top_k=len(pool))
            trace["timings_ms"]["rerank"] = round(
                (time.perf_counter() - t0) * 1000, 1
            )

            before_ids = [c["id"] for c in pool[:top_k]]
            after_ids = [c["id"] for c in reranked[:top_k]]
            trace["stages"].append(
                {
                    "stage": "rerank",
                    "model": settings.rerank_model,
                    "candidates_scored": len(pool),
                    "top_k_before": before_ids,
                    "top_k_after": after_ids,
                    "changed_top_k": before_ids != after_ids,
                    # Chunks the reranker pulled into the top k from lower
                    # down -- direct evidence it did something.
                    "promoted_into_top_k": [
                        i for i in after_ids if i not in before_ids
                    ],
                    "top": _summarize(reranked, 5),
                }
            )
            candidates = reranked
        except RuntimeError as e:
            trace["stages"].append(
                {"stage": "rerank", "skipped": True, "reason": str(e)}
            )

    # -- Stage 4: MMR ------------------------------------------------------
    if do_mmr and candidates:
        t0 = time.perf_counter()
        before_ids = [c["id"] for c in candidates[:top_k]]
        candidates = apply_mmr(question, candidates, top_k=top_k)
        after_ids = [c["id"] for c in candidates]
        trace["timings_ms"]["mmr"] = round((time.perf_counter() - t0) * 1000, 1)
        trace["stages"].append(
            {
                "stage": "mmr",
                "lambda": settings.mmr_lambda,
                "top_k_before": before_ids,
                "top_k_after": after_ids,
                "changed_top_k": before_ids != after_ids,
            }
        )

    final = candidates[:top_k]
    for rank, item in enumerate(final, start=1):
        item["rank"] = rank

    trace["final_chunk_ids"] = [c["id"] for c in final]
    trace["retrieval_order_before_rerank"] = retrieval_order
    trace["timings_ms"]["total"] = round(
        sum(v for k, v in trace["timings_ms"].items() if k != "total"), 1
    )

    return {"chunks": final, "trace": trace}


def _summarize(chunks: list[dict], n: int) -> list[dict]:
    """Compact per-chunk view for the trace — no full chunk text."""
    out = []
    for rank, c in enumerate(chunks[:n], start=1):
        out.append(
            {
                "rank": rank,
                "id": c["id"],
                "filename": c.get("filename"),
                "page": c.get("page"),
                "score": round(c["score"], 4) if c.get("score") is not None else None,
                "preview": (c.get("text") or "")[:120],
            }
        )
    return out
