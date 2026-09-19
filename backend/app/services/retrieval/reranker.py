"""Cross-encoder reranking — the second-pass scorer.

BI-ENCODER vs CROSS-ENCODER
---------------------------
Your dense search uses a *bi-encoder*: the question and each chunk are
embedded SEPARATELY into vectors, then compared with cosine similarity.
That is why it is fast enough to search a whole corpus -- the chunk
vectors were computed once at ingest time and just sit there.

    question --> [encoder] --> vec_q  \
                                        cosine  --> score
    chunk    --> [encoder] --> vec_d  /

The cost of that speed is that the model never sees the question and the
chunk TOGETHER. It cannot notice "this chunk mentions the exact order type
the question asked about" -- it only ever compared two independent summaries.

A *cross-encoder* concatenates them and runs the pair through the model:

    [question] [SEP] [chunk] --> [transformer] --> relevance score

The model attends across both texts at once, so it is markedly more
accurate. It is also far too slow to score an entire corpus -- which is
exactly why it goes SECOND. Dense/hybrid search cheaply narrows 25 (or
25,000) chunks down to ~20 candidates; the cross-encoder then does the
expensive, accurate ordering of just those 20.

That two-stage shape is the standard retrieve-then-rerank pipeline:

    cheap recall (get the right chunk into the top 20)
        --> expensive precision (get it into the top 3)

WHAT THIS FIXES AND WHAT IT DOES NOT
------------------------------------
Reranking can only reorder what the first stage handed it. If the correct
chunk was never in the candidate list, reranking cannot invent it. So a
reranker raises hit-rate@3 but is capped by recall@candidate_k. If your
eval shows recall@20 is already 100% and hit-rate@3 is 60%, reranking is
the correct fix. If recall@20 is 70%, fix retrieval first.
"""

import threading

_model = None
_load_lock = threading.Lock()
_load_error: str | None = None


def _get_model():
    """Lazily load the cross-encoder. Downloads ~90MB on first use.

    Loaded on demand rather than at import so the app still boots (and the
    baseline still runs) on a machine that has never downloaded the model.
    """
    global _model, _load_error

    if _model is not None:
        return _model
    if _load_error is not None:
        raise RuntimeError(_load_error)

    with _load_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import CrossEncoder

            from app.core.config import settings

            _model = CrossEncoder(settings.rerank_model)
            return _model
        except Exception as e:  # noqa: BLE001 - surfaced to the caller as-is
            _load_error = (
                f"Could not load rerank model: {e}. "
                "First use downloads the model, so this needs network access."
            )
            raise RuntimeError(_load_error) from e


def is_available() -> bool:
    """True if the reranker can be used without raising."""
    try:
        _get_model()
        return True
    except RuntimeError:
        return False


def rerank(question: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Re-score candidates against the question, return top_k best first.

    Each returned chunk keeps its original retriever score under
    `pre_rerank_score` and gains `rerank_score`, so the inspection view can
    show exactly how the ordering changed.
    """
    if not candidates:
        return []

    model = _get_model()
    pairs = [(question, c["text"]) for c in candidates]
    scores = model.predict(pairs)

    out = []
    for cand, score in zip(candidates, scores):
        item = dict(cand)
        item["pre_rerank_score"] = cand.get("score")
        item["rerank_score"] = float(score)
        item["score"] = float(score)
        out.append(item)

    out.sort(key=lambda c: -c["rerank_score"])
    for rank, item in enumerate(out, start=1):
        item["rank"] = rank
    return out[:top_k]
