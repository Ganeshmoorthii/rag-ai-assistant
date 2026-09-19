"""Retrieval metrics — turning "it feels better" into a number.

All three metrics below answer slightly different questions. Reporting the
wrong one is the most common way a retrieval writeup goes wrong.

hit-rate@k  "Did at least one correct chunk appear in the top k?"
            Binary per question, then averaged. This is the headline metric
            for the assignment. It is the right one when the user only needs
            ONE correct chunk to get a good answer -- which is the normal
            case for a Q&A app.

recall@k    "What FRACTION of all correct chunks appeared in the top k?"
            Matters when a question needs several pages (q25 here needs two).
            hit-rate@3 = 1.0 and recall@3 = 0.5 means you found one of the
            two pages needed -- the answer will be half right and hit-rate
            will not tell you.

MRR         "How HIGH did the first correct chunk rank?"
            1/rank of the first correct hit, averaged. Sensitive in a way
            hit-rate is not: moving the gold chunk from rank 3 to rank 1
            leaves hit-rate@3 unchanged but lifts MRR from 0.33 to 1.0.
            Use it to detect an improvement that hit-rate@3 hides.

WHY TRACK ALL THREE
-------------------
A change can raise hit-rate@3 while lowering MRR (it drags more gold
chunks in, but ranks them worse). Reporting only the flattering number is
how people fool themselves. Report the set.
"""


def _page_key(filename: str | None, page) -> tuple:
    """Normalise a (filename, page) pair for comparison.

    Metadata round-trips through JSON and SQLite, so page can arrive as
    int or str; filenames vary in surrounding whitespace.
    """
    fn = (filename or "").strip().lower()
    try:
        pg = int(page)
    except (TypeError, ValueError):
        pg = page
    return (fn, pg)


def expected_keys(expected: list[dict]) -> set[tuple]:
    return {_page_key(e.get("filename"), e.get("page")) for e in expected}


def retrieved_keys(chunks: list[dict]) -> list[tuple]:
    """Ordered list of (filename, page) keys, rank 1 first."""
    return [_page_key(c.get("filename"), c.get("page")) for c in chunks]


def hit_at_k(chunks: list[dict], expected: list[dict], k: int) -> bool:
    """True if any expected page appears in the top k."""
    want = expected_keys(expected)
    got = retrieved_keys(chunks)[:k]
    return any(g in want for g in got)


def recall_at_k(chunks: list[dict], expected: list[dict], k: int) -> float:
    """Fraction of expected pages found in the top k."""
    want = expected_keys(expected)
    if not want:
        return 0.0
    got = set(retrieved_keys(chunks)[:k])
    return len(want & got) / len(want)


def first_hit_rank(chunks: list[dict], expected: list[dict]) -> int | None:
    """1-based rank of the first correct chunk, or None if never found."""
    want = expected_keys(expected)
    for i, g in enumerate(retrieved_keys(chunks), start=1):
        if g in want:
            return i
    return None


def reciprocal_rank(chunks: list[dict], expected: list[dict]) -> float:
    """1/rank of the first correct chunk; 0.0 if absent."""
    rank = first_hit_rank(chunks, expected)
    return (1.0 / rank) if rank else 0.0


def aggregate(per_question: list[dict], k_values: list[int]) -> dict:
    """Roll per-question results up into corpus-level metrics.

    Each entry in `per_question` must have `chunks` and `expected`.
    """
    n = len(per_question)
    if n == 0:
        return {"n": 0}

    out: dict = {"n": n}

    for k in k_values:
        hits = sum(1 for r in per_question if hit_at_k(r["chunks"], r["expected"], k))
        recalls = [recall_at_k(r["chunks"], r["expected"], k) for r in per_question]
        out[f"hit_rate@{k}"] = round(hits / n, 4)
        out[f"recall@{k}"] = round(sum(recalls) / n, 4)

    rrs = [reciprocal_rank(r["chunks"], r["expected"]) for r in per_question]
    out["mrr"] = round(sum(rrs) / n, 4)
    out["never_found"] = sum(1 for r in rrs if r == 0.0)

    return out


def aggregate_by_category(per_question: list[dict], k: int) -> dict:
    """hit-rate@k broken down by question category.

    This is the breakdown that answers "which failures did my change NOT
    fix?" -- a corpus-wide average hides that hybrid search fixed every
    exact_term question and none of the vague_phrasing ones.
    """
    buckets: dict[str, list[dict]] = {}
    for r in per_question:
        buckets.setdefault(r.get("category") or "uncategorised", []).append(r)

    out = {}
    for cat, rows in sorted(buckets.items()):
        hits = sum(1 for r in rows if hit_at_k(r["chunks"], r["expected"], k))
        out[cat] = {
            "n": len(rows),
            "hits": hits,
            f"hit_rate@{k}": round(hits / len(rows), 4),
        }
    return out
