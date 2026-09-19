# Week 4 Practical: Failure Separation and One Retrieval Change

## Golden set

The submission set is [backend/eval/golden_set.jsonl](backend/eval/golden_set.jsonl). It contains 12 real developer questions from the two ingested developer documents. The known-correct chunk is recorded as `expected_chunk_id`; the filename and page are retained as a human-readable cross-check. Eight questions contain exact identifiers, endpoints, status codes, or a wildcard token, exceeding the four-question requirement.

The corpus was unchanged between runs: 25 chunks, `top_k=3`, `rrf_k=60`, and the same embedding model. Chunk IDs below are the IDs currently persisted in ChromaDB.

## Baseline

Baseline was measured before enabling hybrid retrieval: dense vector search only, 9/12 hits at 3, or **75.0% hit-rate@3**. The baseline run used the same 12 questions that appear in the after run.

## Failure inspection and labels

All three baseline misses were opened in the Inspector view. There were no generation failures because no baseline miss had the expected chunk in its top 3; there were no Not-In-Corpus cases because every expected chunk exists in the persisted corpus.

| Question | Label | One line of inspection evidence |
|---|---|---|
| q01, `BILL-RESTOCK` | R | Dense top 3 were Advita pages 14, 6, and 10; expected chunk `b3f816c32b0b46c1bf5520e689f981d8_1` on page 2 was absent. |
| q15, `disableSecurityCheck` | R | Dense ranked the expected Cim page 6 at rank 4, outside the top 3; pages 5, 7, and 10 were returned. |
| q18, user impersonation | R | Dense returned Cim pages 10, 7, and 8; expected chunk `def7d74f135e4c439c1ac7e5ed80d3ef_2` on page 3 was absent. |

**Tally: R = 3, G = 0, Not-In-Corpus = 0.**

## One change

I enabled **BM25 + dense retrieval fused with reciprocal rank fusion**, with `rrf_k=60`, by changing only `hybrid_enabled` from `False` to `True` in [backend/app/core/config.py](backend/app/core/config.py). This is justified by the tally: two of the three failures are exact-token misses, where BM25 can match the literal identifier even when dense retrieval blurs it. The implementation uses rank fusion rather than adding BM25 and cosine scores. No reranker, rewrite, HyDE, MMR, chunking, or embedding-model change was included.

## Before and after

Latency was measured in one warmed Python process, one sequential request per question, using external elapsed time around `retriever.retrieve`; process startup and model loading were excluded. The p50 is the median of the 12 query times.

| Run | Hits / 12 | Hit-rate@3 | p50 latency |
|---|---:|---:|---:|
| Baseline: dense | 9/12 | 75.0% | 123.17 ms |
| After: hybrid + RRF | 11/12 | 91.7% | 120.34 ms |
| Delta | +2 | **+16.7 pp** | -2.83 ms |

The latency delta is small and noisy on this local corpus. It is reported as measured, not as evidence that BM25 is faster; the added BM25 and fusion work should be benchmarked under production load before making an SLO claim.

As a reproducibility check after the edit, a second warmed pass produced p50 values of 143.89 ms (baseline) and 144.32 ms (hybrid), while reproducing the exact 9/12 and 11/12 hit counts and the same per-question movement. This variance is why the shipping decision treats latency as neutral rather than as a performance win.

## Per-question movement

| ID | Baseline rank | Hybrid rank | Result |
|---|---:|---:|---|
| q01 | miss | miss | still broken |
| q02 | 1 | 1 | unchanged hit |
| q03 | 1 | 1 | unchanged hit |
| q06 | 1 | 1 | unchanged hit |
| q08 | 1 | 1 | unchanged hit |
| q09 | 1 | 1 | unchanged hit |
| q12 | 2 | 2 | unchanged hit |
| q13 | 2 | 2 | unchanged hit |
| q15 | miss | 1 | **fixed** |
| q17 | 2 | 1 | improved hit |
| q18 | miss | 3 | **fixed** |
| q20 | 1 | 1 | unchanged hit |

The original R-failures fixed were **q15** and **q18**. q15 is the direct exact-token rescue: dense rank 4, BM25 rank 1, and RRF promoted page 6 to rank 1. q18 was pulled from dense rank 4 into the hybrid top 3 at rank 3. **q01 was not fixed at all**: BM25 found page 2 at rank 1, but dense never put page 2 in its candidate top 20 and RRF's agreement preference kept pages 14, 6, and 5 ahead of it. This is an upstream chunking/corpus-layout problem, not evidence to swap embeddings.

## Shipping decision

**Ship hybrid + RRF for this week's change.** It raises the same-set hit-rate@3 from **75.0% to 91.7%**, fixes two of three inspected retrieval failures, and does not regress any of the nine baseline hits. The remaining q01 failure is explicitly known and untouched. The measured p50 moved from **123.17 ms to 120.34 ms**, but that 2.83 ms difference is too small to treat as a performance win; validate latency at realistic concurrency before promising it operationally.

The code diff is exactly one retrieval behavior change: the default hybrid flag in [backend/app/core/config.py](backend/app/core/config.py). The baseline remains reproducible through the evaluation harness with `hybrid=False`.