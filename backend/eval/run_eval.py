"""Retrieval evaluation harness.

Runs the golden set through the retrieval pipeline under a named
configuration and reports hit-rate@k, recall@k and MRR -- overall and
broken down by question category.

USAGE (from the backend/ directory, venv active)
------------------------------------------------
    # 1. Baseline: exactly last week's app (dense only)
    python -m eval.run_eval --config baseline --save

    # 2. One change at a time
    python -m eval.run_eval --config hybrid --save
    python -m eval.run_eval --config rerank --save
    python -m eval.run_eval --config rewrite --save

    # 3. Compare any two saved runs
    python -m eval.run_eval --compare baseline hybrid

    # 4. Everything at once (leaderboard; also writes each run)
    python -m eval.run_eval --sweep --save

    # See exactly which chunks came back for one question
    python -m eval.run_eval --config hybrid --question q01 --verbose

Results are written to eval/results/<config>.json so before/after
comparisons survive across sessions.
"""

import argparse
import asyncio
import json
import os
import sys

# Make `app` importable when run as `python -m eval.run_eval` from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import metrics, retriever  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_PATH = os.path.join(HERE, "golden_set.json")
RESULTS_DIR = os.path.join(HERE, "results")

# Named configurations. Each differs from `baseline` in ONE dimension --
# that is the whole point. If you change two things at once you cannot
# attribute the delta.
CONFIGS: dict[str, dict] = {
    "baseline": {
        "hybrid": False, "rerank": False, "rewrite": False, "mmr": False,
        "_desc": "Dense vector search only — the Week 3 app, unchanged",
    },
    "hybrid": {
        "hybrid": True, "rerank": False, "rewrite": False, "mmr": False,
        "_desc": "BM25 + dense, fused with RRF",
    },
    "rerank": {
        "hybrid": False, "rerank": True, "rewrite": False, "mmr": False,
        "_desc": "Dense top-20 candidates, reordered by a cross-encoder",
    },
    "rewrite": {
        "hybrid": False, "rerank": False, "rewrite": True, "mmr": False,
        "_desc": "LLM rewrites the question, then dense search",
    },
    "hyde": {
        "hybrid": False, "rerank": False, "rewrite": False, "mmr": False,
        "hyde": True,
        "_desc": "LLM writes a hypothetical answer, embeds that, then dense search",
    },
    "mmr": {
        "hybrid": False, "rerank": False, "rewrite": False, "mmr": True,
        "_desc": "Dense + MMR diversity filter",
    },
    "hybrid_rerank": {
        "hybrid": True, "rerank": True, "rewrite": False, "mmr": False,
        "_desc": "Hybrid retrieval then cross-encoder rerank (stacked)",
    },
    "everything": {
        "hybrid": True, "rerank": True, "rewrite": True, "mmr": True,
        "_desc": "All strategies on — a ceiling check, NOT a valid single change",
    },
}

K_VALUES = [1, 3, 5]
HEADLINE_K = 3


def load_golden() -> list[dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


async def run_config(
    name: str, questions: list[dict], top_k: int, only_question: str | None = None
) -> dict:
    """Run every golden question through one named configuration."""
    if name not in CONFIGS:
        raise SystemExit(
            f"Unknown config '{name}'. Choose from: {', '.join(CONFIGS)}"
        )

    cfg = {k: v for k, v in CONFIGS[name].items() if not k.startswith("_")}
    rows = []

    for q in questions:
        if only_question and q["id"] != only_question:
            continue

        result = await retriever.retrieve(q["question"], top_k=top_k, **cfg)
        chunks = result["chunks"]

        rank = metrics.first_hit_rank(chunks, q["expected"])
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "category": q.get("category"),
                "expected": q["expected"],
                "chunks": [
                    {
                        "rank": c.get("rank"),
                        "filename": c.get("filename"),
                        "page": c.get("page"),
                        "score": round(c["score"], 4)
                        if c.get("score") is not None
                        else None,
                        "id": c.get("id"),
                    }
                    for c in chunks
                ],
                "first_hit_rank": rank,
                f"hit@{HEADLINE_K}": metrics.hit_at_k(chunks, q["expected"], HEADLINE_K),
                "reciprocal_rank": round(metrics.reciprocal_rank(chunks, q["expected"]), 4),
                "trace": result["trace"],
            }
        )

    overall = metrics.aggregate(rows, K_VALUES)
    by_cat = metrics.aggregate_by_category(rows, HEADLINE_K)

    return {
        "config_name": name,
        "config": cfg,
        "description": CONFIGS[name]["_desc"],
        "top_k": top_k,
        "overall": overall,
        "by_category": by_cat,
        "questions": rows,
    }


def save_run(run: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{run['config_name']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run, f, indent=2)
    return path


def load_run(name: str) -> dict:
    path = os.path.join(RESULTS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise SystemExit(
            f"No saved run for '{name}'. Run: python -m eval.run_eval "
            f"--config {name} --save"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- reporting ------------------------------------------------------------

def print_run(run: dict, verbose: bool = False) -> None:
    o = run["overall"]
    print()
    print("=" * 72)
    print(f"CONFIG: {run['config_name']}   (top_k={run['top_k']})")
    print(f"  {run['description']}")
    print(f"  flags: {run['config']}")
    print("=" * 72)
    print(f"  questions evaluated : {o['n']}")
    for k in K_VALUES:
        print(
            f"  hit-rate@{k}         : {o[f'hit_rate@{k}']:.1%}"
            f"     recall@{k}: {o[f'recall@{k}']:.1%}"
        )
    print(f"  MRR                 : {o['mrr']:.4f}")
    print(f"  never found at all  : {o['never_found']} / {o['n']}")

    print(f"\n  --- hit-rate@{HEADLINE_K} by category ---")
    for cat, s in run["by_category"].items():
        bar = "#" * int(s[f"hit_rate@{HEADLINE_K}"] * 20)
        print(
            f"  {cat:<16} {s['hits']}/{s['n']:<3} "
            f"{s[f'hit_rate@{HEADLINE_K}']:>6.1%}  {bar}"
        )

    misses = [q for q in run["questions"] if not q[f"hit@{HEADLINE_K}"]]
    if misses:
        print(f"\n  --- MISSES at k={HEADLINE_K} ({len(misses)}) ---")
        for q in misses:
            rank = q["first_hit_rank"]
            where = f"found at rank {rank}" if rank else "NEVER retrieved"
            exp = ", ".join(f"{e['filename']} p.{e['page']}" for e in q["expected"])
            print(f"  [{q['id']}] {q['category']:<15} {where}")
            print(f"        Q: {q['question'][:70]}")
            print(f"        want: {exp}")
            got = ", ".join(f"p.{c['page']}" for c in q["chunks"][:HEADLINE_K])
            print(f"        got : {got}")

    if verbose:
        print("\n  --- FULL DETAIL ---")
        for q in run["questions"]:
            print(f"\n  [{q['id']}] {q['question']}")
            print(f"    expected: {q['expected']}")
            if q["trace"].get("search_query") != q["trace"].get("original_question"):
                print(f"    rewritten -> {q['trace'].get('search_query')}")
            for c in q["chunks"]:
                exp_keys = metrics.expected_keys(q["expected"])
                is_hit = metrics._page_key(c["filename"], c["page"]) in exp_keys
                mark = "HIT " if is_hit else "    "
                print(
                    f"    {mark}#{c['rank']} {c['filename']} p.{c['page']} "
                    f"score={c['score']}"
                )
            for st in q["trace"]["stages"]:
                if st["stage"] == "rrf_fusion" and st.get("bm25_only_in_top_k"):
                    print(f"    BM25-only contributions: {st['bm25_only_in_top_k']}")
                if st["stage"] == "rerank" and st.get("promoted_into_top_k"):
                    print(f"    reranker promoted: {st['promoted_into_top_k']}")
    print()


def print_comparison(before: dict, after: dict) -> None:
    """The before/after table — this is the deliverable."""
    b, a = before["overall"], after["overall"]

    print()
    print("=" * 72)
    print(f"BEFORE  ->  AFTER      ({before['config_name']} -> {after['config_name']})")
    print("=" * 72)

    def delta(metric: str, pct: bool = True) -> None:
        bv, av = b[metric], a[metric]
        d = av - bv
        arrow = "UP  " if d > 0 else ("DOWN" if d < 0 else "same")
        if pct:
            print(
                f"  {metric:<14} {bv:>7.1%}  ->  {av:>7.1%}   "
                f"{arrow} {d:+.1%}"
            )
        else:
            print(
                f"  {metric:<14} {bv:>7.4f}  ->  {av:>7.4f}   "
                f"{arrow} {d:+.4f}"
            )

    for k in K_VALUES:
        delta(f"hit_rate@{k}")
    print()
    for k in K_VALUES:
        delta(f"recall@{k}")
    print()
    delta("mrr", pct=False)

    print(f"\n  --- hit-rate@{HEADLINE_K} by category ---")
    cats = sorted(set(before["by_category"]) | set(after["by_category"]))
    key = f"hit_rate@{HEADLINE_K}"
    for cat in cats:
        bc = before["by_category"].get(cat, {})
        ac = after["by_category"].get(cat, {})
        bv, av = bc.get(key, 0.0), ac.get(key, 0.0)
        d = av - bv
        flag = "  <-- FIXED" if d > 0 else ("  <-- REGRESSED" if d < 0 else "")
        print(
            f"  {cat:<16} {bv:>6.1%} -> {av:>6.1%}  "
            f"({bc.get('hits', 0)}/{bc.get('n', 0)} -> "
            f"{ac.get('hits', 0)}/{ac.get('n', 0)}){flag}"
        )

    # Per-question movement: fixed, broken, and still-broken.
    bq = {q["id"]: q for q in before["questions"]}
    aq = {q["id"]: q for q in after["questions"]}
    hk = f"hit@{HEADLINE_K}"

    fixed, broke, still = [], [], []
    for qid in sorted(set(bq) & set(aq)):
        was, now = bq[qid][hk], aq[qid][hk]
        if not was and now:
            fixed.append(qid)
        elif was and not now:
            broke.append(qid)
        elif not was and not now:
            still.append(qid)

    print(f"\n  FIXED by this change ({len(fixed)}): {', '.join(fixed) or 'none'}")
    for qid in fixed:
        print(
            f"    [{qid}] {aq[qid]['category']:<15} rank "
            f"{bq[qid]['first_hit_rank']} -> {aq[qid]['first_hit_rank']}"
        )
        print(f"          {aq[qid]['question'][:64]}")

    print(f"\n  BROKEN by this change ({len(broke)}): {', '.join(broke) or 'none'}")
    for qid in broke:
        print(
            f"    [{qid}] {aq[qid]['category']:<15} rank "
            f"{bq[qid]['first_hit_rank']} -> {aq[qid]['first_hit_rank']}"
        )
        print(f"          {aq[qid]['question'][:64]}")

    # The question your mentor explicitly asks: what did it NOT fix?
    print(f"\n  STILL BROKEN — not fixed by this change ({len(still)}): "
          f"{', '.join(still) or 'none'}")
    for qid in still:
        print(f"    [{qid}] {aq[qid]['category']:<15} {aq[qid]['question'][:56]}")
    print()


def print_sweep(runs: list[dict]) -> None:
    print()
    print("=" * 88)
    print("LEADERBOARD — all configurations")
    print("=" * 88)
    hdr = f"  {'config':<16}"
    for k in K_VALUES:
        hdr += f" hit@{k}  "
    hdr += "  MRR     miss"
    print(hdr)
    print("  " + "-" * 84)

    base = next((r for r in runs if r["config_name"] == "baseline"), None)
    for r in sorted(runs, key=lambda x: -x["overall"][f"hit_rate@{HEADLINE_K}"]):
        o = r["overall"]
        line = f"  {r['config_name']:<16}"
        for k in K_VALUES:
            line += f" {o[f'hit_rate@{k}']:>6.1%} "
        line += f"  {o['mrr']:.4f}  {o['never_found']:>3}"
        if base and r["config_name"] != "baseline":
            d = o[f"hit_rate@{HEADLINE_K}"] - base["overall"][f"hit_rate@{HEADLINE_K}"]
            line += f"   ({d:+.1%} vs baseline)"
        print(line)
    print()


async def main() -> None:
    ap = argparse.ArgumentParser(
        description="Measure retrieval quality against the golden set."
    )
    ap.add_argument("--config", help=f"one of: {', '.join(CONFIGS)}")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"),
                    help="compare two saved runs")
    ap.add_argument("--sweep", action="store_true",
                    help="run every config and print a leaderboard")
    ap.add_argument("--question", help="evaluate only this question id (e.g. q01)")
    ap.add_argument("--top-k", type=int, default=HEADLINE_K,
                    help=f"how many chunks to retrieve (default {HEADLINE_K})")
    ap.add_argument("--save", action="store_true",
                    help="write results to eval/results/<config>.json")
    ap.add_argument("--verbose", action="store_true",
                    help="print every retrieved chunk")
    ap.add_argument("--list-configs", action="store_true")
    args = ap.parse_args()

    if args.list_configs:
        print("\nAvailable configurations:\n")
        for name, cfg in CONFIGS.items():
            flags = {k: v for k, v in cfg.items() if not k.startswith("_")}
            print(f"  {name:<16} {cfg['_desc']}")
            print(f"  {'':<16} {flags}\n")
        return

    if args.compare:
        print_comparison(load_run(args.compare[0]), load_run(args.compare[1]))
        return

    questions = load_golden()
    n = retriever.ensure_bm25_index(force=True)
    print(f"\nBM25 index built over {n} chunks.")
    if n == 0:
        raise SystemExit(
            "No chunks in the vector store — upload your PDFs first."
        )

    if args.sweep:
        runs = []
        for name in CONFIGS:
            print(f"  running {name}...")
            try:
                run = await run_config(name, questions, args.top_k)
            except Exception as e:  # noqa: BLE001
                print(f"    skipped {name}: {e}")
                continue
            runs.append(run)
            if args.save:
                save_run(run)
        print_sweep(runs)
        return

    if not args.config:
        ap.error("pass --config NAME, or --sweep, or --compare BEFORE AFTER")

    run = await run_config(args.config, questions, args.top_k, args.question)
    print_run(run, verbose=args.verbose)
    if args.save and not args.question:
        print(f"  saved -> {save_run(run)}\n")
    elif args.save:
        print("  not saved (partial run: --question was set)\n")


if __name__ == "__main__":
    asyncio.run(main())
