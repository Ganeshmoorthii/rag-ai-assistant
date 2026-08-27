# Week 4 · M2 — Debugging Retrieval

Hybrid search, reranking, and failure separation, measured on this project's
own corpus (`Advita DOCs.pdf`, `Cim Authentication.pdf` — 25 chunks).

---

## 1. The one idea that matters

"The app is wrong" is **two different bugs wearing the same coat**, and they
have opposite fixes.

| | What happened | The fix | What does NOT help |
|---|---|---|---|
| **Retrieval failure** | The right chunk never reached the LLM | Hybrid search, reranking, query rewriting, chunking | A smarter/bigger model. It answered correctly given what it was handed — it was handed the wrong thing. |
| **Generation failure** | The right chunk **was** in the context, answer still wrong | Prompt, chunk size, model | Better retrieval. Retrieval already did its job. |

The whole point of this week is that you stop guessing which one you have.
The test is mechanical: **was a correct chunk in the top k, or not?**

```
Question ─→ Retriever ─→ [chunks] ─→ LLM ─→ Answer
                            │
                    was the right chunk here?
                    NO  → retrieval failure
                    YES → generation failure
```

---

## 2. Baseline: what was actually broken

Measured over 25 golden questions, `top_k=3`, dense search only (the Week 3 app):

```
hit-rate@1  72.0%      recall@1  66.0%
hit-rate@3  88.0%      recall@3  84.0%
MRR         0.8000     never found at all: 3 / 25
```

Three real failures, and the triage endpoint classified **all three as
retrieval failures** — the correct page was never in the top 3:

| id | question | wanted | got instead |
|---|---|---|---|
| q01 | What does `BILL-RESTOCK` mean? | Advita p.2 | p.14, p.6, p.10 |
| q15 | What happens if `disableSecurityCheck` is true? | CimAuth p.6 | p.5, p.7, p.10 |
| q18 | How does user impersonation work? | CimAuth p.3 | p.10, p.7, p.8 |

This is why "just use a better model" would have been wasted money: the
answer text was never in the context window.

---

## 3. Results: one change at a time

Every configuration differs from `baseline` in exactly **one** dimension.

| config | hit@1 | hit@3 | MRR | still missing |
|---|---|---|---|---|
| baseline (dense only) | 72.0% | 88.0% | 0.8000 | 3 |
| **hybrid** (BM25+RRF) | 80.0% | **96.0%** | 0.8733 | 1 |
| **rerank** (cross-encoder) | **88.0%** | **96.0%** | **0.9200** | 1 |
| rewrite (LLM) | 68.0% | 88.0% | 0.7800 | 3 |
| hyde | 72.0% | 88.0% | 0.8000 | 3 |
| mmr | 72.0% | 88.0% | 0.7867 | 3 |
| hybrid + rerank (stacked) | 88.0% | 96.0% | 0.9200 | 1 |

### The headline number

**hit-rate@3: 88.0% → 96.0% (+8 percentage points)** with one change.

Two configs tie on hit-rate@3. **Reranking is the better single change**,
because it also wins on the metrics hit-rate@3 cannot see:

- hit-rate@1: 72% → **88%** (+16pp) — hybrid only reached 80%
- MRR: 0.80 → **0.92** — hybrid only reached 0.87

Same number of right answers in the top 3, but reranking puts them **first**.

### Why hybrid worked — the evidence for q15

From the inspector trace, for *"What happens if disableSecurityCheck is true?"*:

```
dense  ranked the correct page (CimAuth p.6) at #4   ← missed at k=3
bm25   ranked the correct page at #1                 ← exact identifier match
RRF    fused them → correct page at #1               ← FIXED
```

The badge in the UI reads `dense #4 | bm25 #1`. That single line is the proof:
keyword search found what semantic search missed, because
`disableSecurityCheck` is a rare literal token, and BM25 weights rare tokens
heavily while an embedding model blurs them into "security config stuff".

---

## 4. What the change did NOT fix

**q01 — "What does BILL-RESTOCK mean?" is still broken in every config.**

This is the most interesting result, so here it is in full. BM25 *does* rank
the correct page (p.2) at **#1**. It still loses:

```
dense top-5:  p.14  p.6   p.10  p.5   p.3      ← p.2 not in top 20 at all
bm25  top-5:  p.2   p.14  p.13  p.5   p.6      ← p.2 is #1
fused:        p.14  p.6   p.5   p.13  p.3      ← p.2 lost
```

**Why:** `BILL-RESTOCK` appears in 5 of 25 chunks, so its IDF is only
moderate — no single chunk dominates. Meanwhile p.14 is ranked #1 by dense
*and* #2 by BM25, so RRF rewards it for **agreement** across retrievers.
p.2 gets one contribution (1/61); p.14 gets two (1/61 + 1/62).

RRF is working exactly as designed. Rewarding agreement is the feature, and
here the feature costs us the answer.

I checked whether this was just bad tuning — it is not:

| rrf_k | 1 | 5 | 10 | 20 | 60 |
|---|---|---|---|---|---|
| hit@3 | 96% | 92% | 96% | 96% | 96% |

Flat. No fusion constant rescues q01, because **dense search never surfaces
p.2 at all**, so fusion has only one vote to work with. Reranking cannot fix
it either — a reranker can only reorder candidates retrieval already found.

**The real fix for q01 is chunking, not retrieval.** The definition of
`BILL-RESTOCK` sits in a wide table split across pages 2–3, so the row
label and its meaning land in different chunks. That is next week's problem,
and it is a good example of a failure that *looks* like retrieval and is
actually upstream of it.

### Also not fixed

- **Query rewriting made things worse** (MRR 0.80 → 0.78). Paraphrasing
  destroys the exact identifiers these questions depend on. Real cost, zero
  benefit, on this corpus.
- **MMR slightly hurt** (MRR 0.80 → 0.787). Expected: MMR optimises for
  covering *distinct* information, and 24 of 25 golden questions have a
  single correct page. A single-gold-chunk metric cannot reward diversity.
- **`*` and `-L` tokenise poorly** (q20, q04). `tokenize("wildcard * permission")`
  drops the `*` entirely. Visible in the inspector's `terms:` line.

---

## 5. A bug worth recording

The first `rewrite` run scored **84%** — worse than baseline. Before blaming
the technique, I read the actual rewriter output:

```
Q:  "hey so the thing where the rep gets money taken off, how much is it"
->  "The user is asking about "the thing where the rep gets money taken
     off" - this sounds like a commission deduction, fee, or penalty..."
```

The configured model (`nvidia/nemotron-3-ultra-550b-a55b:free`) is a
**reasoning model**: it emitted its chain-of-thought instead of a query. That
monologue was then embedded, so the search probe was meta-commentary *about*
the question rather than the question. `_clean_rewrite()` in
[query_rewriter.py](backend/app/services/query_rewriter.py) now strips it.

**Lesson:** when a technique underperforms, look at its intermediate output
before concluding the technique is wrong. After the fix, rewriting recovered
to 88% — genuinely neutral, not broken.

---

## 6. How to reproduce

```bash
cd backend
.venv/Scripts/python -m eval.run_eval --config baseline --save
.venv/Scripts/python -m eval.run_eval --config hybrid   --save
.venv/Scripts/python -m eval.run_eval --config rerank   --save

# the before/after table
.venv/Scripts/python -m eval.run_eval --compare baseline rerank

# everything, ranked
.venv/Scripts/python -m eval.run_eval --sweep --save

# inspect one question in detail
.venv/Scripts/python -m eval.run_eval --config hybrid --question q15 --verbose
```

In the UI (`npm run dev` + `uvicorn app.main:app`):

- **Inspector** — pick a golden question, toggle strategies, hit
  *Diagnose this failure*. Shows the verdict, every retrieved chunk, which
  retriever found it, and the answer side by side.
- **Measurement** — run configs, pick a before and after, get the delta plus
  Fixed / Broke / Still-broken lists.

---

## 7. The concepts, briefly

**BM25** — keyword scoring that weights *rare* words heavily.
`ERR-4032` in 1 chunk of 25 scores high; "the" scores ~0. `k1=1.5` saturates
repeated terms; `b=0.75` stops long chunks winning by length alone.
Implemented from scratch in [bm25.py](backend/app/services/bm25.py) — no new
dependency.

**Keyword vs semantic** — semantic matches *meaning* ("how does restocking
work"), keyword matches *characters* (`BILL-RESTOCK`). Embeddings squash rare
identifiers into the same region: `BILL-RESTOCK`, `BILL-ONLY` and
`RESTOCK-ONLY` are semantically near-identical and operationally opposite.

**Hybrid + RRF** — run both, fuse by **rank** not score:
`score = Σ 1/(k + rank)`. Ranks are scale-free, so no weight tuning; dense
similarity (0–1) and BM25 (unbounded) never need normalising.

**Cross-encoder reranking** — a bi-encoder embeds question and chunk
*separately* (fast, searchable, but never sees them together). A cross-encoder
runs `[question] [SEP] [chunk]` through the model *jointly* — much more
accurate, far too slow for a whole corpus. So: cheap recall to ~20 candidates,
then expensive precision on those 20. Capped by `recall@candidate_k`.

**MMR** — greedy diversity: `λ·relevance − (1−λ)·max_similarity_to_picked`.
Fights near-duplicate chunks (you use 150-word overlap). λ=0.7 default.

**Query rewriting / HyDE** — rewriting makes the question look like a *query*;
HyDE makes it look like an *answer* (generate a hypothetical passage, embed
that). HyDE's insight: you are searching answer-shaped documents, so
document→document similarity beats question→document. The invented passage
can be factually wrong — it is only a retrieval probe.

**Metrics** — `hit-rate@k`: did *any* correct chunk make the top k (binary).
`recall@k`: what *fraction* of correct chunks made it (matters for q25, which
needs two pages). `MRR`: how *high* the first correct chunk ranked — catches
improvements hit-rate@3 hides. Report all three; a change can raise one and
lower another.

---

## 8. Files

| file | what it does |
|---|---|
| [bm25.py](backend/app/services/bm25.py) | BM25 index, pure Python |
| [retriever.py](backend/app/services/retriever.py) | pipeline + RRF + MMR + tracing |
| [reranker.py](backend/app/services/reranker.py) | cross-encoder second pass |
| [query_rewriter.py](backend/app/services/query_rewriter.py) | rewrite + HyDE |
| [metrics.py](backend/app/services/metrics.py) | hit-rate, recall, MRR |
| [golden_set.json](backend/eval/golden_set.json) | 25 questions, keyed on filename+page |
| [run_eval.py](backend/eval/run_eval.py) | CLI harness |
| [InspectorPanel.jsx](frontend/src/components/InspectorPanel.jsx) | the inspection view |
| [EvalPanel.jsx](frontend/src/components/EvalPanel.jsx) | before/after in the UI |

All strategies default to **off** in [config.py](backend/app/core/config.py),
so `baseline` is genuinely last week's app.
