# Week 5 Error Taxonomy — Developer Documentation RAG

| Mode Name | Count | Freq % | Severity | Example Trace ID |
|---|:---:|:---:|---|---|
| `v2_signature_returned_for_v3_query` | 7 | 35.0% | Ships broken code to user repo | `tr_042` |
| `omitted_prerequisite_header_or_import` | 4 | 20.0% | Ships broken code to user repo | `tr_050` |
| `wildcard_and_special_char_token_dropped` | 4 | 20.0% | Merely annoys the reader | `tr_048` |
| `numeric_status_code_confusion` | 3 | 15.0% | Merely annoys the reader | `tr_067` |
| `partial_multihop_context_truncation` | 2 | 10.0% | Merely annoys the reader | `tr_097` |

---

### Key Takeaways
- **Top Priority**: `v2_signature_returned_for_v3_query` accounts for **35.0%** of total real-world failures and directly causes users to copy-paste non-compiling/deprecated v2 SDK methods.
- **Critical Severity**: Combined with `omitted_prerequisite_header_or_import` (20.0%), **55.0%** of all failures result in broken code executing in developer environments.
- **Fix Order**: Attack `v2_signature_returned_for_v3_query` first via metadata filtering on `sdk_version`.
