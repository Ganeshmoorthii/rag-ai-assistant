# Week 5 Dated Prediction — Target Fix Strategy

- **Date**: 2026-09-01
- **Target Failure Mode**: `v2_signature_returned_for_v3_query` (Top failure mode, 35.0% frequency)
- **Specific Change**: Introduce explicit metadata filtering on `sdk_version` (e.g., `sdk_version: v3`) in `vector_store.query()` and `bm25.search()`, combined with query transformer version extraction.
- **Expected Delta**: Reduce the occurrence of `v2_signature_returned_for_v3_query` from **35.0% (7/20)** down to **under 5.0% (<1/20)** on random developer query traces, while raising hit-rate@3 on versioned SDK queries from 65% to >90%.
