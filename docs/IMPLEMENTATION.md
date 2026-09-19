# AI-Assistant — Complete Implementation Reference

A full-stack Retrieval-Augmented Generation (RAG) system with a debuggable
retrieval pipeline, a measurable evaluation harness, and an error-analysis
workflow built on replayable interaction traces.

This document is the single, exhaustive reference for **how the entire project
is implemented** — every module, every stage of the pipeline, every endpoint,
every UI panel, the maths behind the retrieval strategies, the measured
results, and the known gaps.

> **Scope note.** This is an implementation reference, not a tutorial.
> For the narrative writeup of the Week 4 retrieval investigation see
> [RETRIEVAL_DEBUGGING.md](RETRIEVAL_DEBUGGING.md); for the Week 5 error
> analysis see [notes.md](notes.md), [taxonomy.md](taxonomy.md) and
> [prediction.md](prediction.md); for quickstart instructions see
> [README.md](README.md).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Timeline and Evolution](#2-project-timeline-and-evolution)
3. [Repository Layout](#3-repository-layout)
4. [System Architecture](#4-system-architecture)
5. [Technology Stack and Dependency Rationale](#5-technology-stack-and-dependency-rationale)
6. [Configuration System](#6-configuration-system)
7. [Ingestion Pipeline](#7-ingestion-pipeline)
8. [Storage Layer — ChromaDB](#8-storage-layer--chromadb)
9. [The BM25 Keyword Index](#9-the-bm25-keyword-index)
10. [The Retrieval Pipeline](#10-the-retrieval-pipeline)
11. [Query Transformation — Rewrite and HyDE](#11-query-transformation--rewrite-and-hyde)
12. [Cross-Encoder Reranking](#12-cross-encoder-reranking)
13. [MMR Diversity Filtering](#13-mmr-diversity-filtering)
14. [The Trace Object](#14-the-trace-object)
15. [Generation Layer](#15-generation-layer)
16. [Trace Logging and Replay](#16-trace-logging-and-replay)
17. [Evaluation System](#17-evaluation-system)
18. [Measured Results](#18-measured-results)
19. [Error Analysis Workflow](#19-error-analysis-workflow)
20. [HTTP API Reference](#20-http-api-reference)
21. [Frontend Architecture](#21-frontend-architecture)
22. [End-to-End Walkthrough](#22-end-to-end-walkthrough)
23. [Operations — Setup, Run, Debug](#23-operations--setup-run-debug)
24. [Known Issues and Limitations](#24-known-issues-and-limitations)
25. [Roadmap](#25-roadmap)
26. [Appendix A — File Index](#appendix-a--file-index)
27. [Appendix B — Configuration Reference](#appendix-b--configuration-reference)
28. [Appendix C — Glossary](#appendix-c--glossary)
29. [Appendix D — Commit History](#appendix-d--commit-history)

---

## 1. Executive Summary

### What the system does

Upload PDFs. Ask questions about them. Get answers grounded in the actual
document text, with filename + page citations for every claim.

That is the surface. Underneath, the project's real subject is **why RAG
systems fail and how to prove which half is broken**:

- A question can fail because retrieval never surfaced the right chunk
  (**retrieval failure**), or because the right chunk was in context and the
  model still answered badly (**generation failure**). These have opposite
  fixes, and guessing wrong wastes weeks.
- The system makes that distinction mechanical via a `/api/triage` endpoint
  and a golden set of questions with known-correct pages.
- Every retrieval strategy (hybrid search, reranking, query rewriting, HyDE,
  MMR) is individually switchable *per request*, and every stage writes into a
  structured trace, so any claimed improvement can be attributed to exactly
  one change and measured with a before/after number.

### The three capabilities

| Capability | Where it lives | What it proves |
|---|---|---|
| **Answering** | `POST /api/query`, Chat tab | The product works |
| **Debugging** | `POST /api/triage`, Retrieval Inspector tab | *Which* half is broken, for one question |
| **Measuring** | `POST /api/evaluate`, `eval/run_eval.py`, Measurement tab | Whether a change helped, across 25 questions |

### Headline numbers

Measured on this repository's own corpus (2 PDFs, 25 indexed chunks) against
25 golden questions at `top_k=3`:

| Configuration | hit@1 | hit@3 | recall@3 | MRR | never found |
|---|---:|---:|---:|---:|---:|
| baseline (dense only) | 72.0% | 88.0% | 84.0% | 0.8000 | 3 / 25 |
| hybrid (BM25 + RRF) | 80.0% | **96.0%** | 90.0% | 0.8733 | 1 / 25 |
| rerank (cross-encoder) | **88.0%** | **96.0%** | **92.0%** | **0.9200** | 1 / 25 |
| hybrid + rerank | **88.0%** | **96.0%** | **92.0%** | **0.9200** | 1 / 25 |
| rewrite (LLM) | 68.0% | 88.0% | 84.0% | 0.7800 | 3 / 25 |
| hyde | 72.0% | 88.0% | 84.0% | 0.8000 | 3 / 25 |
| mmr | 72.0% | 88.0% | 82.0% | 0.7867 | 3 / 25 |

**+8 percentage points on hit-rate@3 from one change.** Reranking is the
stronger single change because it also lifts hit@1 by 16pp and MRR by 0.12 —
metrics that hit-rate@3 is structurally blind to.

### Scale of the codebase

| Layer | Files | Approx. lines |
|---|---:|---:|
| Backend application (`backend/app/`) | 20 | ~1,500 |
| Evaluation harness (`backend/eval/`) | 5 | ~900 |
| Frontend (`frontend/src/`) | 10 | ~2,650 |
| Documentation (root `*.md`) | 6 | ~540 |
| **Total tracked files** | **69** | — |

---

## 2. Project Timeline and Evolution

The repository was built in weekly increments, each of which added one
capability layer rather than rewriting the previous one.

### Week 3 — the baseline app

Upload a PDF, chunk it, embed it locally, store it in ChromaDB, retrieve the
top-K by cosine similarity, hand those chunks to an LLM, return the answer with
citations. This is the `baseline` configuration in the evaluation harness, and
it is still reachable today by setting every strategy flag to `false`.

Everything after this point is additive. **The baseline was never deleted** —
that is deliberate, because a baseline you cannot re-run is not a baseline.

### Week 4 — debugging retrieval

Commit `d140e3b` (2026-08-27) introduced the retrieval assistant UI with upload,
chat, evaluation and inspection panels. This week added:

- BM25 keyword search, implemented from scratch (`bm25.py`)
- Reciprocal Rank Fusion to combine dense + keyword results
- Cross-encoder reranking (`reranker.py`)
- LLM query rewriting and HyDE (`query_rewriter.py`)
- MMR diversity filtering
- Retrieval metrics: hit-rate@k, recall@k, MRR (`metrics.py`)
- A 25-question golden set keyed on filename + page
- A CLI evaluation harness with per-config result persistence
- A per-stage trace emitted with every query
- The `/api/triage` retrieval-vs-generation classifier

Commit `d40edc4` fixed error handling in `generate_answer` and a candidate
filtering bug in `apply_mmr` (candidates missing embeddings were being scored
as maximally novel and jumping to the top).

Deliverables: [RETRIEVAL_DEBUGGING.md](RETRIEVAL_DEBUGGING.md) and
[results.md](results.md).

### Week 4.5 — UI maturity

Commits `1626a3c`, `507f6bf`, `18b03c2` (2026-08-30) rebuilt the frontend on a
Tailwind design-token system, replaced emoji/text affordances with a
hand-rolled inline SVG icon set (21 icons, zero icon-library dependency), and
added markdown rendering for assistant answers.

### Week 5 — error analysis

Commits `165ac86` → `cdfac10` (2026-09-01 to 2026-09-05):

- `eval/generate_traces.py` — a deterministic generator producing 100
  replayable developer-documentation interaction traces across 5 seeded
  failure modes
- `eval/replay_trace.py` — a seeded sampler and offline replay engine that
  reconstructs the exact prompt from a trace record alone, plus a schema audit
- `app/services/trace_logger.py` — live trace persistence, so real user queries
  land in the same JSONL format as the generated dataset
- Provider switching (OpenRouter ⇄ Groq) via a single boolean

Deliverables: [notes.md](notes.md), [taxonomy.md](taxonomy.md),
[prediction.md](prediction.md).

### Week 5.5 — chunk transparency

Commits `38c5388`, `5a7c7c4` (2026-09-05) added GFM table rendering and the
**Document Chunks Explorer**: a `GET /api/chunks` endpoint plus a searchable,
filterable UI over every chunk in the index. This closes the loop on the Week 4
finding that q01's failure was a *chunking* problem, not a retrieval problem —
you now inspect chunk boundaries directly instead of inferring them.

---

## 3. Repository Layout

```
AI-Assistant/
├── README.md                       Quickstart, API summary, config table
├── RETRIEVAL_DEBUGGING.md          Week 4 narrative writeup
├── IMPLEMENTATION.md               ← this document
├── results.md                      Week 4 practical: failure separation
├── notes.md                        Week 5 error analysis notes
├── taxonomy.md                     Week 5 failure-mode taxonomy
├── prediction.md                   Week 5 dated falsifiable prediction
├── .gitignore
├── .vscode/
│   └── launch.json                 FastAPI debug config (subProcess: true)
│
├── backend/
│   ├── requirements.txt            13 pinned dependencies
│   ├── .env.example                Every setting, documented
│   ├── .env                        Local secrets (gitignored)
│   │
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, lifespan, /health
│   │   │
│   │   ├── core/
│   │   │   ├── config.py           Pydantic Settings — the single source of truth
│   │   │   └── flow_log.py         Structured console tracing
│   │   │
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py     Router aggregation
│   │   │   │   ├── documents.py    Upload / list / chunks / delete
│   │   │   │   ├── query.py        The main Q&A endpoint
│   │   │   │   └── evaluation.py   Triage, evaluate, configs, settings
│   │   │   └── schemas/
│   │   │       ├── documents.py    UploadResponse, DocumentInfo, ChunkInfo
│   │   │       ├── query.py        QueryRequest, SourceChunk, QueryResponse
│   │   │       └── evaluation.py   Triage + Eval request/response models
│   │   │
│   │   └── services/
│   │       ├── pdf_loader.py       pypdf text extraction + OCR fallback
│   │       ├── chunker.py          Word-window chunking with overlap
│   │       ├── ingest.py           Orchestrates load → chunk → store
│   │       ├── vector_store.py     ChromaDB wrapper (the only Chroma import)
│   │       ├── bm25.py             BM25 index, pure Python, no dependency
│   │       ├── retriever.py        The pipeline: RRF, MMR, tracing
│   │       ├── reranker.py         Cross-encoder second pass
│   │       ├── query_rewriter.py   Rewrite + HyDE + reasoning-model cleanup
│   │       ├── llm_client.py       Provider-agnostic chat completion
│   │       ├── metrics.py          hit-rate@k, recall@k, MRR
│   │       └── trace_logger.py     Live interaction persistence
│   │
│   ├── eval/
│   │   ├── golden_set.json         25 questions (the measurement set)
│   │   ├── golden_set.jsonl        12 questions (the Week 4 submission set)
│   │   ├── run_eval.py             CLI harness: run, compare, sweep
│   │   ├── generate_traces.py      100-trace dataset generator
│   │   ├── replay_trace.py         Seeded sampler + offline replay
│   │   └── results/                One JSON per saved configuration run
│   │       ├── baseline.json  hybrid.json  hybrid_rerank.json
│   │       └── hyde.json      mmr.json     rerank.json  rewrite.json
│   │
│   └── data/
│       ├── chroma/                 Persistent vector DB (gitignored)
│       ├── uploads/                Original PDFs (gitignored)
│       └── traces.jsonl            104 interaction traces (tracked)
│
└── frontend/
    ├── package.json                React 18 + Vite 5 + Tailwind 3
    ├── vite.config.js              Dev server on :5173
    ├── tailwind.config.js          Custom dark palette + shadow tokens
    ├── postcss.config.js
    ├── index.html
    └── src/
        ├── main.jsx                React root
        ├── App.jsx                 Shell + 4-tab navigation
        ├── api.js                  All 10 fetch wrappers
        ├── index.css               489 lines of design-system CSS
        ├── lib/utils.js            cn() — clsx + tailwind-merge
        └── components/
            ├── DocumentPanel.jsx   Upload (drag-drop) + document list
            ├── ChatPanel.jsx       Conversational Q&A
            ├── InspectorPanel.jsx  The retrieval debugger (730 lines)
            ├── EvalPanel.jsx       Before/after measurement
            ├── ChunksPanel.jsx     Chunk explorer (458 lines)
            └── icons.jsx           21 inline SVG icons
```

### Layering rules

The backend follows a strict three-layer separation, and it holds throughout:

```
routes/     HTTP concerns only. Parse, validate, delegate, shape response.
            No business logic. No direct ChromaDB access.
   ↓
services/   All logic. Framework-agnostic — importable from a CLI script
            with no FastAPI in the process (which is exactly what
            eval/run_eval.py does).
   ↓
core/       Configuration and cross-cutting utilities. Imported by
            everything, imports nothing from the layers above.
```

Two consequences worth stating explicitly:

1. **`vector_store.py` is the only module that imports `chromadb`.** Swapping
   for Qdrant, pgvector or FAISS is a single-file change.
2. **The evaluation harness runs the production pipeline, not a copy of it.**
   `eval/run_eval.py` imports `app.services.retriever` directly. There is no
   parallel "eval version" of retrieval that can silently drift from what
   ships.

---

## 4. System Architecture

### The two flows

```
════════════════════════ INGESTION (once per PDF) ════════════════════════

  PDF upload
      │
      ▼
  routes/documents.py ── validate .pdf, uuid-prefix filename, write to disk
      │
      ▼
  services/ingest.py ──── orchestrator
      │
      ├─▶ pdf_loader.extract_text_by_page()
      │       pypdf per page  ──▶ empty? ──▶ pdf2image (Poppler)
      │                                          ▼
      │                                    pytesseract OCR @ 300 DPI
      │
      ├─▶ chunker.chunk_text()  ── 1000-word windows, 150-word overlap
      │
      └─▶ vector_store.add_chunks()
              SentenceTransformer all-MiniLM-L6-v2 → 384-dim vectors
              ChromaDB PersistentClient, cosine space
      │
      ▼
  retriever.invalidate_bm25_index() ── force a full in-memory rebuild
      │
      ▼
  { doc_id, filename, chunks: N }


════════════════════════ QUERY (per question) ════════════════════════════

  question + per-request strategy flags
      │
      ▼
  routes/query.py ──── flow_log, resolve config, delegate
      │
      ▼
  services/retriever.retrieve()
      │
      ├── Stage 1  query transform ....... rewrite | HyDE | passthrough
      │
      ├── Stage 2  candidate retrieval
      │              dense  ── vector_store.query(search_query, fetch_n)
      │              bm25   ── bm25.index.search(ORIGINAL question, fetch_n)
      │              fuse   ── reciprocal_rank_fusion({dense, bm25})
      │
      ├── Stage 3  rerank ................ cross-encoder over top candidate_k
      │
      ├── Stage 4  MMR ................... greedy diversity selection
      │
      └── slice to top_k, assign ranks, finalise trace
      │
      ▼
  services/llm_client.generate_answer()
      build context block → POST to OpenRouter | Groq → extract answer
      │
      ▼
  services/trace_logger.log_interaction_trace() ── append to traces.jsonl
      │
      ▼
  { answer, sources[], trace{} }
```

### Design principles the code actually follows

**1. Every stage is optional and independently switchable.**
`hybrid`, `rerank`, `rewrite`, `mmr`, `hyde` each resolve from
per-request override → `.env` default. Turning on exactly one at a time is
what makes a measured delta attributable.

**2. Every stage records what it did.**
The trace is not logging. It is a first-class return value that reaches the
API response and the UI. `retriever.retrieve()` returns
`{"chunks": [...], "trace": {...}}` — the trace is half the contract.

**3. Optional stages fail open.**
A rewriter outage returns the original question. A missing cross-encoder model
records `{"stage": "rerank", "skipped": true, "reason": ...}` and continues.
MMR with no embeddings returns the input order. Degraded retrieval beats a
500.

**4. Scores are normalised in direction, never in magnitude.**
`vector_store.query()` converts Chroma's cosine *distance* to `1 - dist` so
that across every retriever, **bigger always means better**. Magnitudes are
deliberately *not* normalised — RRF discards them anyway (§10.3).

**5. Ground truth is keyed on `(filename, page)`, not chunk id.**
Chunk ids are `{doc_id}_{index}` and regenerate on every re-upload. Filename +
page survives re-ingestion, so the golden set does not rot.

---

## 5. Technology Stack and Dependency Rationale

### Backend — `backend/requirements.txt`

| Package | Version | Role | Why this one |
|---|---|---|---|
| `fastapi` | 0.115.0 | HTTP framework | Async-native, Pydantic-integrated, free OpenAPI docs |
| `uvicorn[standard]` | 0.32.0 | ASGI server | `--reload` for dev; `[standard]` pulls httptools/uvloop |
| `python-multipart` | 0.0.12 | Multipart parsing | Required by FastAPI for `UploadFile` |
| `pydantic` | 2.9.2 | Validation | Request/response schemas |
| `pydantic-settings` | 2.6.0 | Config | `.env` → typed `Settings` object |
| `chromadb` | 0.5.20 | Vector DB | Embedded, persistent, zero infra — no Docker required |
| `sentence-transformers` | 3.2.1 | Embeddings + reranker | Local inference: no per-query embedding cost, no data leaving the machine |
| `pypdf` | 5.1.0 | PDF text | Pure Python, per-page extraction |
| `httpx` | 0.27.2 | HTTP client | Async, needed because the routes are async |
| `python-dotenv` | 1.0.1 | `.env` loading | Used via pydantic-settings |
| `pytesseract` | 0.3.13 | OCR | Tesseract binding for scanned pages |
| `pdf2image` | 1.17.0 | PDF → image | Poppler binding, feeds OCR |
| `Pillow` | 11.0.0 | Imaging | pdf2image dependency |

**System binaries** (not pip-installable, required only for the OCR fallback):

- **Poppler** — provides `pdfinfo`/`pdftoppm`. Point `POPPLER_PATH` at its
  `Library\bin` directory, or leave blank to use `PATH`.
- **Tesseract OCR** — provides `tesseract.exe`. Point `TESSERACT_CMD` at the
  binary, or leave blank to use `PATH`.

**Notably absent:** there is no `rank_bm25` package. BM25 is ~200 lines of
`bm25.py`, written by hand — partly to avoid a dependency, mostly because the
tokenizer needed custom behaviour that off-the-shelf BM25 does not provide
(§9.1).

### Frontend — `frontend/package.json`

| Package | Version | Role |
|---|---|---|
| `react` / `react-dom` | 18.3.1 | UI runtime |
| `vite` | 5.4.9 | Dev server + bundler |
| `@vitejs/plugin-react` | 4.3.2 | Fast Refresh |
| `tailwindcss` | 3.4.13 | Utility CSS |
| `postcss` / `autoprefixer` | 8.5.26 / 10.5.4 | CSS pipeline |
| `react-markdown` | 10.1.0 | Render LLM markdown answers |
| `remark-gfm` | 4.0.1 | GitHub-flavoured markdown — tables in answers |
| `clsx` + `tailwind-merge` | 2.1.1 / 3.6.0 | `cn()` class composition |
| `class-variance-authority` | 0.7.1 | Variant helper |

**No state library, no router, no component library, no icon package.** Four
tabs of `useState`, hand-written SVG icons, and a CSS design system in
`index.css`. The dependency surface stays small enough to audit.

### The embedding model

`sentence-transformers/all-MiniLM-L6-v2`:

- 384-dimensional output, ~90 MB on disk
- 6 transformer layers — fast enough to embed a whole PDF in seconds on CPU
- Downloaded once on first use, cached locally afterwards
- Runs **entirely locally**: document text is never sent to an embedding API

The cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`, also ~90 MB) is a
separate lazy download, triggered only the first time reranking is enabled.

---

## 6. Configuration System

### The Settings object — `backend/app/core/config.py`

A single Pydantic `BaseSettings` subclass is the only source of configuration
truth. It reads `backend/.env`, falls back to the declared defaults, and is
instantiated once at import time as the module-level `settings` singleton.

```python
class Settings(BaseSettings):
    # --- LLM provider ---
    openrouter_enabled: bool = True
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    groq_model: str = "openai/gpt-oss-20b"

    # --- Embeddings and storage ---
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"

    # --- Tracing ---
    traces_path: str = "./data/traces.jsonl"
    trace_logging_enabled: bool = True

    # --- Chunking and retrieval ---
    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4

    # --- OCR binaries ---
    tesseract_cmd: str = ""
    poppler_path: str = ""

    # --- Week 4 strategy toggles ---
    hybrid_enabled: bool = True
    candidate_k: int = 20
    rrf_k: int = 60

    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int = 20

    rewrite_enabled: bool = False
    rewrite_model: str = ""       # blank = reuse openrouter_model

    mmr_enabled: bool = False
    mmr_lambda: float = 0.7

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

### Provider switching

Four computed properties turn one boolean into a complete provider swap. No
call site anywhere in the codebase branches on which provider is active:

```python
@property
def llm_api_key(self) -> str:
    return self.openrouter_api_key if self.openrouter_enabled else self.groq_api_key

@property
def llm_model(self) -> str:
    return self.openrouter_model if self.openrouter_enabled else self.groq_model

@property
def llm_url(self) -> str:
    if self.openrouter_enabled:
        return "https://openrouter.ai/api/v1/chat/completions"
    return "https://api.groq.com/openai/v1/chat/completions"

@property
def llm_provider(self) -> str:
    return "OpenRouter" if self.openrouter_enabled else "Groq"
```

This works because both providers expose an OpenAI-compatible
`/chat/completions` shape. Adding a third provider means adding one branch to
each of these four properties.

### Three-level precedence

Strategy flags resolve in a strict order, and this is what makes the whole
evaluation methodology possible:

```
1. Per-request value      QueryRequest.hybrid = True
       ↓  (if None)
2. .env / Settings        settings.hybrid_enabled
       ↓  (if unset)
3. Class default          hybrid_enabled: bool = True
```

Implemented in `retriever.retrieve()`:

```python
top_k      = settings.top_k           if top_k   is None else top_k
hybrid     = settings.hybrid_enabled  if hybrid  is None else hybrid
do_rerank  = settings.rerank_enabled  if rerank  is None else rerank
do_rewrite = settings.rewrite_enabled if rewrite is None else rewrite
do_mmr     = settings.mmr_enabled     if mmr     is None else mmr
```

Because `None` means "inherit" rather than "off", the eval harness can run
seven different configurations against **one running server and one warm
index** without restarts. That is the difference between a 30-second sweep and
a 30-minute one — and it eliminates index-state drift between runs as a
confound.

### Flow logging — `backend/app/core/flow_log.py`

Ten lines that make one question traceable through the console:

```python
def flow_log(event: str, **data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=True, default=str)
    print(f"[QUESTION FLOW] {event} {payload}", flush=True)
```

`default=str` means no serialisation crash on unexpected types. `flush=True`
means ordering is preserved under `--reload`. Events emitted across a single
query:

```
request.received  →  retrieval.started  →  [query_transform.*]
   →  retrieval.dense_results  →  retrieval.bm25_results
   →  retrieval.rrf_results    →  [retrieval.rerank_results | rerank_skipped]
   →  [retrieval.mmr_results]  →  retrieval.completed
   →  llm.request.started      →  llm.response.received
   →  llm.answer.extracted     →  response.completed  →  trace.logged
```

Response headers are filtered to strip `authorization` and `set-cookie` before
logging. The API key itself is never logged — only the provider name and model
id.

---

## 7. Ingestion Pipeline

### 7.1 Upload endpoint — `routes/documents.py`

```python
@router.post("/documents", response_model=UploadResponse)
async def upload_document(file: UploadFile):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(settings.upload_dir, safe_name)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    result = ingest_pdf(dest_path, file.filename)
    if result["chunks"] == 0:
        os.remove(dest_path)
        raise HTTPException(status_code=422, detail="No text could be extracted...")

    retriever.invalidate_bm25_index()
    return UploadResponse(**result)
```

Four decisions worth noting:

1. **UUID prefix on the stored filename** prevents collisions between two
   uploads named `report.pdf`, while the *original* filename is what gets
   stored in chunk metadata and shown in citations.
2. **Zero-chunk uploads are rejected with 422 and the file is deleted.** An
   image-only PDF that also fails OCR would otherwise sit on disk as a
   document with no retrievable content — visible in the UI, useless in
   search.
3. **The BM25 index is invalidated synchronously**, before the response
   returns. The next query therefore cannot see a stale keyword index.
4. **Ingestion is synchronous.** For a 20-page PDF this is a few seconds and
   the UI shows an "Indexing…" overlay. For a 500-page corpus this needs a
   background task — see §25.

### 7.2 Text extraction and OCR — `services/pdf_loader.py`

```python
if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _ocr_page(file_path: str, page_number: int) -> str:
    kwargs = {"first_page": page_number, "last_page": page_number, "dpi": 300}
    if settings.poppler_path:
        kwargs["poppler_path"] = settings.poppler_path

    images = convert_from_path(file_path, **kwargs)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0]).strip()


def extract_text_by_page(file_path: str) -> list[dict]:
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if not text:
            text = _ocr_page(file_path, i + 1)
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages
```

**The OCR fallback is per page, not per document.** A PDF with 18 text pages
and 2 scanned pages runs OCR on exactly 2 pages. Since OCR at 300 DPI costs
roughly a second per page versus milliseconds for `pypdf`, whole-document OCR
would be a 100× regression on the common case.

**Page numbers are 1-based** (`i + 1`) because that is what a human reads off
the PDF viewer and what the citation shows.

**Empty pages are dropped entirely** rather than stored as blank chunks —
blank chunks pollute BM25's `avgdl` and waste vector-store rows.

**Poppler path resolution is the most common setup failure.** `poppler_path`
overrides `PATH` completely: if it is set to a directory that does not exist,
`pdf2image` raises `PDFInfoNotInstalledError` even when Poppler *is* correctly
installed and on `PATH`. A blank `POPPLER_PATH` is the safer setting once the
binaries are on `PATH`; a hardcoded absolute path copied from another machine
is the failure mode to watch for.

### 7.3 Chunking — `services/chunker.py`

```python
def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    words = text.split()
    if not words:
        return []

    chunks = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
    return chunks
```

A sliding word window: 1000 words wide, stepping 850 words, so consecutive
chunks share 150 words.

**Worked example** — a 2,400-word page with `chunk_size=1000`, `overlap=150`,
`step=850`:

| Chunk | Word range | Length | Overlaps with |
|---|---|---:|---|
| 0 | 0 – 999 | 1000 | — |
| 1 | 850 – 1849 | 1000 | chunk 0 on words 850–999 |
| 2 | 1700 – 2399 | 700 | chunk 1 on words 1700–1849 |

The loop breaks after chunk 2 because `1700 + 1000 ≥ 2400`, which prevents the
trailing sliver chunk a naive range loop would emit.

**Why words rather than tokens or characters.** Word counts are stable across
tokenizer versions and human-legible when debugging ("this chunk is ~1000
words" is checkable; "this chunk is 1,340 tokens" is not, without running the
tokenizer). The cost is that the model's actual token budget is only
approximated — roughly 1.3 tokens per English word, so a 1000-word chunk is
~1,300 tokens.

**Why overlap at all.** Without it, a fact spanning a boundary is destroyed:
the sentence "the discrepancy penalty is Item Cost × 1.4" could split into
"…the discrepancy penalty is" / "Item Cost × 1.4" and neither chunk answers the
question. 150 words of overlap means any fact shorter than 150 words appears
intact in at least one chunk.

**The cost of overlap** is duplication: ~15% of the corpus is stored twice, and
near-duplicate chunks compete for the same top-k slots. That is precisely the
problem MMR exists to address (§13).

**Chunking is page-scoped.** `ingest.py` chunks each page independently, so a
chunk never spans a page boundary — which is what keeps the `page` metadata
field meaningful, and therefore what keeps `(filename, page)` viable as the
ground-truth key. The trade-off is real and was measured: a table split across
pages 2–3 loses the association between a row label and its meaning, which is
exactly the unfixable q01 failure documented in §18.4.

### 7.4 Orchestration — `services/ingest.py`

```python
def ingest_pdf(file_path: str, filename: str) -> dict:
    doc_id = new_doc_id()
    pages = extract_text_by_page(file_path)

    chunks = []
    for page in pages:
        for chunk in chunk_text(page["text"]):
            chunks.append({"text": chunk, "page": page["page"]})

    count = add_chunks(doc_id, filename, chunks)
    return {"doc_id": doc_id, "filename": filename, "chunks": count}
```

Sixteen lines, three service calls, no logic of its own. The value is the
seam: the pipeline is `extract → chunk → store`, and each piece is swappable
without touching the others.

---

## 8. Storage Layer — ChromaDB

### 8.1 Client and collection — `services/vector_store.py`

```python
_client = chromadb.PersistentClient(path=settings.chroma_dir)

_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=settings.embedding_model
)

_collection = _client.get_or_create_collection(
    name="documents",
    embedding_function=_embedding_fn,
    metadata={"hnsw:space": "cosine"},
)
```

Three module-level singletons, created once at import:

- **`PersistentClient`** writes to `./data/chroma` — a SQLite file plus HNSW
  index segments. Data survives restarts with no external service.
- **The embedding function is attached to the collection**, so Chroma embeds
  on `add()` and on `query(query_texts=...)` automatically. Documents and
  queries are therefore guaranteed to use the same model — a class of bug that
  simply cannot occur here.
- **`hnsw:space: cosine`** because sentence-transformer embeddings are
  direction-meaningful; Euclidean distance on unnormalised vectors would rank
  by magnitude as much as by meaning.

### 8.2 Writing chunks

```python
def add_chunks(doc_id: str, filename: str, chunks: list[dict]) -> int:
    if not chunks:
        return 0

    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {"doc_id": doc_id, "filename": filename, "page": c["page"], "chunk_index": i}
        for i, c in enumerate(chunks)
    ]

    _collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)
```

The id scheme `{doc_id}_{index}` gives deterministic, sortable, human-readable
ids. `b3f816c3..._4` is the fifth chunk of that document — you can find it by
eye in a trace.

Four metadata fields carry everything downstream needs:

| Field | Consumer |
|---|---|
| `doc_id` | delete-by-document, chunk filtering |
| `filename` | citations, golden-set matching |
| `page` | citations, golden-set matching |
| `chunk_index` | stable ordering in the Chunks Explorer |

### 8.3 Dense query

```python
def query(question: str, top_k: int | None = None) -> list[dict]:
    top_k = settings.top_k if top_k is None else top_k
    results = _collection.query(query_texts=[question], n_results=top_k)

    matches = []
    ids   = results.get("ids") or [[]]
    docs  = results.get("documents") or [[]]
    metas = results.get("metadatas") or [[]]
    dists = results.get("distances") or [[]]

    for cid, text, meta, dist in zip(ids[0], docs[0], metas[0], dists[0]):
        matches.append({
            "id": cid,
            "text": text,
            "filename": meta.get("filename"),
            "page": meta.get("page"),
            "doc_id": meta.get("doc_id"),
            "score": 1 - dist,     # distance → similarity
        })
    return matches
```

Two details that matter downstream:

- **`1 - dist`.** Chroma returns cosine *distance* (lower is better). BM25
  returns a score (higher is better). Converting here means every consumer —
  fusion, reranking, the UI, the trace — can assume higher is better. Without
  this, sort direction becomes a per-retriever special case and eventually
  someone gets it backwards.
- **The chunk `id` is returned.** Fusion needs a stable identity to recognise
  that dense rank 4 and BM25 rank 1 are the *same chunk*. Without ids, RRF is
  impossible.

### 8.4 The remaining accessors

| Function | Returns | Used by |
|---|---|---|
| `get_all_chunks()` | every chunk with metadata | BM25 index rebuild |
| `get_chunks(doc_id=None)` | chunks + `word_count`, `char_count`, sorted | `GET /api/chunks`, Chunks Explorer |
| `get_embeddings(ids)` | `{id: vector}` for specific chunks | MMR redundancy computation |
| `embed_query(text)` | one vector via the corpus embedding fn | MMR relevance computation |
| `list_documents()` | `[{doc_id, filename, chunks}]` | `GET /api/documents` |
| `delete_document(doc_id)` | — (deletes by `where` filter) | `DELETE /api/documents/{id}` |
| `new_doc_id()` | `uuid4().hex` | ingestion |

`get_chunks()` does a small amount of defensive repair worth noting: if
`chunk_index` is missing from metadata (documents ingested before that field
existed), it recovers the index by parsing the id suffix:

```python
chunk_idx = meta.get("chunk_index")
if chunk_idx is None and "_" in cid:
    try:
        chunk_idx = int(cid.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        chunk_idx = 0
elif chunk_idx is None:
    chunk_idx = 0
```

Results are then sorted by `(filename.lower(), chunk_index, page)` so the
Chunks Explorer shows documents in reading order rather than storage order.

`get_embeddings()` guards a real Chroma quirk: `data.get("embeddings")` can be
`None` rather than an empty list, and individual embeddings can be `None`.
Both cases are handled explicitly, because MMR treating a missing embedding as
a zero vector would make that chunk look maximally novel and promote it to the
top of the results (the bug fixed in commit `d40edc4`).

---

## 9. The BM25 Keyword Index

`backend/app/services/bm25.py` — ~200 lines, pure Python, no dependency.

### 9.1 Why keyword search exists here at all

Dense embedding search matches on **meaning**. That is exactly right for
*"how does restocking work?"* and exactly wrong for *"what does `BILL-RESTOCK`
mean?"*.

An embedding model squashes rare tokens into a shared region of vector space.
`BILL-RESTOCK`, `BILL-ONLY` and `RESTOCK-ONLY` are semantically near-identical
and **operationally opposite** — one is counted as revenue, one is not. Cosine
similarity cannot separate them, because separating them is not what cosine
similarity does.

BM25 matches on **exact words**, and weights rare words heavily. A token that
appears in 1 chunk out of 25 gets a large IDF, so the chunk that literally
contains `S0A59667` wins outright. That is precisely the failure mode dense
search cannot fix by itself, no matter how good the embedding model gets.

### 9.2 The scoring formula

For a query `Q` and a document `D`:

```
score(D, Q) = Σ over each query term q of

                IDF(q) · ( f(q,D) · (k1 + 1) )
                ─────────────────────────────────────────
                ( f(q,D) + k1 · (1 − b + b · len(D)/avgdl) )
```

| Symbol | Meaning | Value here |
|---|---|---|
| `f(q,D)` | term frequency of `q` in `D` | computed at build time |
| `len(D)` | document length in tokens | computed at build time |
| `avgdl` | mean document length in the corpus | computed at build time |
| `IDF(q)` | how rare `q` is — the important part | smoothed, see below |
| `k1` | term-frequency saturation | **1.5** |
| `b` | length normalisation | **0.75** |

**`k1 = 1.5` saturates term frequency.** The 10th occurrence of a word adds far
less than the 2nd. Without saturation, keyword-stuffed chunks would dominate
purely by repetition.

**`b = 0.75` normalises for length.** Without it, long chunks win simply by
containing more words. With `b = 1` normalisation is total; with `b = 0` there
is none. 0.75 is the standard compromise.

**Smoothed IDF:**

```python
def _idf(self, term: str) -> float:
    n = len(self._doc_len)
    df = self._df.get(term, 0)
    if df == 0:
        return 0.0
    return math.log(1 + (n - df + 0.5) / (df + 0.5))
```

A term in 1 of 25 chunks scores high; a term in all 25 scores about 0. The
`+0.5 / +1.0` smoothing keeps the value positive and finite even for terms
present in every document — the unsmoothed classical formula can go negative
there, which would let a common word *penalise* a chunk.

### 9.3 The tokenizer — the reason this is hand-written

```python
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")

def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        raw = raw.strip("-_")
        if not raw:
            continue
        tokens.append(raw)
        # Emit parts of compound identifiers as extra terms.
        if "-" in raw or "_" in raw:
            for part in re.split(r"[-_]+", raw):
                if part:
                    tokens.append(part)
    return tokens
```

**Hyphen and underscore are deliberately word characters.** A naive `\w+`
tokenizer shatters `BILL-RESTOCK` into `bill` + `restock`, which destroys the
exact-match advantage that is the entire reason BM25 was added. Keeping them
means `BILL-RESTOCK`, `cim_`, `320-32-36` and `-L` survive as single
searchable units.

**Compound identifiers are also emitted as parts.** `BILL-RESTOCK` produces
three tokens: `bill-restock`, `bill`, `restock`. So an exact query for
`BILL-RESTOCK` gets the full-token hit *and* a query for just `restock`
partially matches. This is a dual-granularity index in a single pass.

`tokenize("What does BILL-RESTOCK mean?")` produces
`['what', 'does', 'bill-restock', 'bill', 'restock', 'mean']`.

**Known limitation:** the character class excludes `*`, `/`, `.`, `:` and
every other symbol. `tokenize("wildcard * permission")` drops the `*`
entirely, so a question *about* the wildcard character cannot be matched on
that character. This is a documented, measured failure (§18.5) rather than an
oversight — fixing it means either widening the class (which pulls in
punctuation noise) or adding a symbol-alias table.

### 9.4 Index structure and lifecycle

```python
class BM25Index:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: list[str] = []           # chunk ids, positionally aligned
        self._meta: list[dict] = []         # filename / page / doc_id
        self._texts: list[str] = []         # chunk text
        self._tf: list[dict[str, int]] = [] # per-chunk term frequencies
        self._doc_len: list[int] = []       # per-chunk token count
        self._df: dict[str, int] = {}       # corpus document frequencies
        self._avgdl: float = 0.0
        self._built = False
```

Six positionally-aligned lists plus one corpus-wide dict. `build()` clears
everything and re-derives it in a single pass over the records, under a lock.

**The index is in-memory only**, so it must be rebuilt:

- **on process start** — `main.py` does this in the `lifespan` hook, so the
  first query is never the one that pays for the build:

  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      count = retriever.ensure_bm25_index(force=True)
      print(f"[startup] BM25 keyword index built over {count} chunks")
      yield
  ```

- **after every ingest and every delete** — both routes call
  `retriever.invalidate_bm25_index()`, which is a `force=True` rebuild.

**Full rebuild, not incremental update.** For tens to low-thousands of chunks
a rebuild costs milliseconds, and incremental index maintenance is a
well-known source of subtle drift bugs (stale `df` counts, orphaned postings).
The trade is deliberate and it stops being correct somewhere north of ~100k
chunks.

**Thread safety** is a single `threading.Lock` held for the whole of `build()`
and the whole of `search()`. Under uvicorn, requests are served concurrently,
so a query arriving mid-rebuild would otherwise read half-updated lists.

### 9.5 Search

```python
def search(self, query: str, top_k: int) -> list[dict]:
    with self._lock:
        if not self._built or not self._ids:
            return []

        q_terms = tokenize(query)
        if not q_terms:
            return []

        idf_cache = {t: self._idf(t) for t in set(q_terms)}

        scored: list[tuple[float, int]] = []
        for i in range(len(self._ids)):
            tf = self._tf[i]
            dl = self._doc_len[i]
            denom_len = K1 * (1 - B + B * (dl / self._avgdl if self._avgdl else 0))

            score = 0.0
            for term in q_terms:
                f = tf.get(term)
                if not f:
                    continue
                idf = idf_cache[term]
                if idf <= 0:
                    continue
                score += idf * (f * (K1 + 1)) / (f + denom_len)

            if score > 0:
                scored.append((score, i))

        scored.sort(key=lambda x: (-x[0], x[1]))
        ...
```

A linear scan over the corpus — O(chunks × query terms). At 25 chunks this is
microseconds; at 100k chunks it would need an inverted index (map term to
posting list) so only chunks containing a query term are scored at all.

Three efficiency details: IDF is cached once per **distinct** query term;
`denom_len` is computed once per document rather than per term; and chunks
scoring zero are never appended, so the sort operates only on actual matches.
The tie-break `(-score, index)` makes ordering deterministic — important,
because non-deterministic ranking makes before/after comparison meaningless.

---

## 10. The Retrieval Pipeline

`backend/app/services/retriever.py` — the one place every strategy is composed.

### 10.1 Shape

```
                              question
                                 |
      +--------------------------+---------------------------+
      |  Stage 1: query transform (optional)                 |  fix a
      |    rewrite  -> LLM restates it as a search query      |  broken
      |    hyde     -> LLM invents a hypothetical answer      |  question
      +--------------------------+---------------------------+
                                 |
      +--------------------------+---------------------------+
      |  Stage 2: candidate retrieval                        |  fix missed
      |    dense search (embeddings)  --+                    |  exact
      |                                 +-> RRF fusion       |  terms
      |    BM25 search (keywords)     --+                    |
      +--------------------------+---------------------------+
                                 |
      +--------------------------+---------------------------+
      |  Stage 3: cross-encoder rerank (optional)            |  fix bad
      +--------------------------+---------------------------+  ordering
                                 |
      +--------------------------+---------------------------+
      |  Stage 4: MMR diversity filter (optional)            |  fix dup
      +--------------------------+---------------------------+  chunks
                                 |
                    top_k chunks  +  full stage trace
```

Each stage targets a *different* failure. That mapping is the reason the
pipeline is shaped this way, and it is what makes the triage verdict
actionable: knowing *which* stage failed tells you which knob to turn.

### 10.2 Over-fetching for later stages

```python
needs_candidates = hybrid or do_rerank or do_mmr
fetch_n = max(settings.candidate_k, top_k) if needs_candidates else top_k
```

A reranker can only promote a chunk that retrieval already found. MMR can only
diversify among candidates it was handed. So whenever a later stage will
re-order or filter, the first stage fetches `candidate_k` (default 20) instead
of `top_k` (default 3–4).

**`candidate_k` is the ceiling on what the entire pipeline can possibly get
right.** If the correct chunk is not in the top 20, no downstream stage can
recover it. This is why `recall@candidate_k` is the diagnostic to check before
investing in a reranker: if recall@20 is already 100% and hit@3 is 60%, a
reranker is exactly the right fix; if recall@20 is 70%, fix first-stage
retrieval instead.

When no later stage is active, `fetch_n = top_k` — no wasted work on the
baseline path.

### 10.3 Reciprocal Rank Fusion

```python
def reciprocal_rank_fusion(ranked_lists, rrf_k=None) -> list[dict]:
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
```

#### Why RRF instead of a weighted score sum

Dense similarity lives in roughly `0..1`. BM25 is **unbounded** and depends on
corpus statistics — a rare-term match can score 4, or 8, or 15. The two
numbers are not on a common scale, so `0.7*dense + 0.3*bm25` is meaningless:

- the weights would need retuning for every new corpus, and
- a single high-IDF term could swamp the dense signal entirely.

RRF discards scores and keeps only **ranks**:

```
rrf_score(chunk) = Σ over each retriever of  1 / (k + rank)
```

Rank is scale-free. No normalisation, no weight tuning, no corpus-specific
calibration.

#### Worked example, `k = 60`

| Chunk | dense rank | bm25 rank | contributions | rrf_score |
|---|---:|---:|---|---:|
| A | 1 | 1 | 1/61 + 1/61 | **0.03279** |
| B | 1 | — | 1/61 | 0.01639 |
| C | 2 | 3 | 1/62 + 1/63 | 0.03200 |
| D | — | 1 | 1/61 | 0.01639 |

Chunk A wins on **agreement**: both retrievers ranked it first. Chunk C, ranked
2nd and 3rd, still beats chunk B, ranked *1st* by dense alone. Meanwhile chunk
D — invisible to dense search entirely — scores the same as B and therefore
lands in the fused top 4. **That is how exact-term matches get rescued: one
BM25 vote is enough to pull a chunk into contention.**

#### What `k` controls

`k = 60` comes from the original RRF paper. It damps the curve: with `k = 60`
the gap between rank 1 (1/61 ≈ 0.0164) and rank 2 (1/62 ≈ 0.0161) is tiny, so
**agreement across retrievers matters more than being top of any single list**.
A small `k` (say 1) makes rank 1 dominate — 1/2 vs 1/3 is a 50% gap — which
effectively reduces fusion to "whoever won one list wins".

The `rrf_k` sensitivity was measured directly (§18.4): hit@3 is flat at 96%
across `k` in {1, 10, 20, 60} on this corpus, which is evidence that the one
remaining failure is *not* a tuning problem.

#### Provenance is preserved

The `retrievers` dict is the payoff. Every fused chunk carries:

```json
"retrievers": {
  "dense": { "rank": 4, "score": 0.71, "rrf_contribution": 0.015625 },
  "bm25":  { "rank": 1, "score": 8.42, "rrf_contribution": 0.016393 }
}
```

The UI renders this as `dense #4 | bm25 #1`. That single badge is the evidence
that keyword search found what semantic search missed — the difference between
"hybrid feels better" and a defensible claim.

**BM25 always searches the ORIGINAL question**, never the rewritten one:

```python
bm25_results = bm25.index.search(question, top_k=fetch_n)
```

The rewrite is tuned for semantic search. The user's own wording is where exact
identifiers live, and paraphrasing can lose them — which would defeat the
entire purpose of running BM25 alongside.

The fusion stage also records the set arithmetic that makes hybrid's
contribution legible:

```python
dense_ids = {c["id"] for c in dense_results[:top_k]}
bm25_ids  = {c["id"] for c in bm25_results[:top_k]}
trace["stages"].append({
    "stage": "rrf_fusion",
    "rrf_k": settings.rrf_k,
    "fused_count": len(candidates),
    "bm25_only_in_top_k":  sorted(bm25_ids - dense_ids),
    "dense_only_in_top_k": sorted(dense_ids - bm25_ids),
    "agreed_in_top_k":     sorted(dense_ids & bm25_ids),
    "top": _summarize(candidates, 5),
})
```

`bm25_only_in_top_k` is the money line: chunks BM25 contributed that dense
search would have missed entirely.

### 10.4 The full `retrieve()` flow

```python
async def retrieve(question, top_k=None, hybrid=None, rerank=None,
                   rewrite=None, mmr=None, hyde=False) -> dict:
    # 1. resolve every flag: per-request -> .env -> class default
    # 2. initialise the trace skeleton
    # 3. Stage 1 — query transform
    # 4. Stage 2 — dense (+ bm25 + RRF)
    # 5. Stage 3 — rerank
    # 6. Stage 4 — MMR
    # 7. slice to top_k, assign 1-based ranks
    # 8. finalise timings, return {chunks, trace}
    return {"chunks": final, "trace": trace}
```

Every stage is individually timed with `time.perf_counter()`, and the total is
computed as a sum of the parts rather than measured independently:

```python
trace["timings_ms"]["total"] = round(
    sum(v for k, v in trace["timings_ms"].items() if k != "total"), 1
)
```

Note this means `total` is retrieval-stage time only — it does **not** include
LLM generation latency.

Two ordering artifacts are recorded so a reranker's effect is provable:

```python
retrieval_order = [c["id"] for c in candidates[:top_k]]   # captured pre-rerank
...
trace["final_chunk_ids"] = [c["id"] for c in final]
trace["retrieval_order_before_rerank"] = retrieval_order
```

### 10.5 The `_summarize` helper

```python
def _summarize(chunks: list[dict], n: int) -> list[dict]:
    out = []
    for rank, c in enumerate(chunks[:n], start=1):
        out.append({
            "rank": rank,
            "id": c["id"],
            "filename": c.get("filename"),
            "page": c.get("page"),
            "score": round(c["score"], 4) if c.get("score") is not None else None,
            "preview": (c.get("text") or "")[:120],
        })
    return out
```

Every stage trace stores a compact top-5 summary rather than full chunk text.
Without this, a trace over five stages would embed the same 1000-word chunks
five times, and `traces.jsonl` would grow by tens of KB per query. A
120-character preview is enough to recognise a chunk by eye.

---

## 11. Query Transformation — Rewrite and HyDE

`backend/app/services/query_rewriter.py`

### 11.1 The problem being solved

Users do not type search queries. They type things like:

> "hey so the thing where the rep gets money taken off, how much is it"

Nothing in that sentence lexically **or** semantically matches the chunk that
answers it (*"commission is deducted from the rep (Item Cost x 1.4)"*).
Retrieval is not broken — the **query** is broken. No amount of reranking
helps, because the correct chunk never enters the candidate list at all.

Two independent fixes are implemented.

### 11.2 Rewrite

Ask the LLM to restate the question as a dense, keyword-rich search query,
preserving exact identifiers verbatim.

```python
REWRITE_SYSTEM = (
    "You rewrite user questions into concise search queries for a document "
    "retrieval system. Rules:\n"
    "- Keep every exact identifier verbatim: error codes, order types, "
    "field names, endpoints, serial numbers, file paths, ALL_CAPS terms.\n"
    "- Expand vague references into the concrete domain terms implied.\n"
    "- Strip conversational filler and politeness.\n"
    "- Reply with at most 15 words, on a single line.\n"
    "- Output ONLY the rewritten query. No preamble, no reasoning, no "
    "quotes, no explanation, no bullet points."
)
```

The example above becomes something like
`"rep commission deduction amount item cost multiplier"`. Cheap, predictable,
and it keeps exact codes intact — which matters because those codes are what
BM25 keys on.

### 11.3 HyDE — Hypothetical Document Embeddings

A different trick with a neater insight: instead of making the question look
more like a query, make it look like an **answer**.

```python
HYDE_SYSTEM = (
    "You write a short hypothetical passage that would plausibly answer the "
    "user's question, in the style of internal technical documentation. "
    "Two to three sentences. Use the specific vocabulary the real document "
    "would use. Do not hedge, do not say you are unsure, do not mention "
    "that this is hypothetical. Output only the passage."
)
```

**Why it works.** You are searching a corpus of *answer-shaped documents*. A
question and its answer are often lexically dissimilar — "how much is
deducted?" vs "commission is deducted at Item Cost × 1.4" — so
question→document similarity is a mismatch of registers. Document→document
similarity is not.

**The hypothetical answer can be factually wrong and it still works**, because
it is only ever used as a retrieval probe. It lands in the right neighbourhood
of vector space and is then discarded; the real answer comes from the
retrieved chunks.

The original question is appended to the generated passage:

```python
result = f"{doc}\n\n{question}" if doc else question
```

This preserves exact identifiers in the probe even if the LLM paraphrased them
away.

### 11.4 Determinism

```python
payload = {
    "model": model,
    "messages": [...],
    "max_tokens": max_tokens,
    "temperature": 0,          # the same question must rewrite identically
}
```

`temperature = 0` is mandatory here. A non-deterministic rewriter means the
same question produces a different search probe on every run, and your
before/after numbers are then measuring sampling noise rather than the change
you made.

### 11.5 `_clean_rewrite` — a bug worth the whole section

The first `rewrite` evaluation run scored **84%**, below the 88% baseline.
Before blaming the technique, the actual rewriter output was inspected:

```
Q:  "hey so the thing where the rep gets money taken off, how much is it"
->  "The user is asking about "the thing where the rep gets money taken
     off" - this sounds like a commission deduction, fee, or penalty..."
```

The configured model was a **reasoning model**. It ignored "output only the
query" and emitted its chain-of-thought. That monologue was then embedded, so
the search probe became meta-commentary *about* the question rather than the
question — landing in completely the wrong region of vector space.

`_clean_rewrite()` is the defence, and it runs four filters in order:

```python
# 1. Drop <think>...</think> blocks emitted by reasoning models.
text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
text = re.sub(r"<thinking>.*?</thinking>", " ", text, flags=re.S | re.I)

# 2. Prefer an explicitly labelled query line if the model provided one.
labelled = re.search(r"(?:rewritten query|search query|query)\s*[:\-]\s*(.+)", text, re.I)
if labelled:
    text = labelled.group(1)

# 3. Otherwise take the LAST non-empty line — models that think out loud
#    nearly always put the actual deliverable last.
lines = [ln.strip(" \t\"'`*-") for ln in text.splitlines()]
lines = [ln for ln in lines if ln]
candidate = lines[-1]

# 4. Reject anything that still reads as prose about the question.
tells = ("the user is asking", "the user wants", "this sounds like",
         "i need to", "i should", "let me", "could refer to",
         "most likely", "i'll rewrite", "here is", "here's", "rewritten")
if any(t in candidate.lower() for t in tells) or len(candidate.split()) > 25:
    return question
if candidate.endswith((":", ",")) or len(candidate.split()) < 2:
    return question
```

The last check catches truncation: a response cut off by `max_tokens` often
ends mid-sentence on a colon or comma, and is too short to be a real query.

**Every rejection path falls back to the user's original question**, which is
at least guaranteed to be on-topic.

After this fix, rewriting recovered to 88% — genuinely neutral on this corpus,
not broken.

> **The transferable lesson:** when a technique underperforms, read its
> intermediate output before concluding the technique is wrong. The trace
> exists precisely so that output is one click away.

### 11.6 Graceful degradation

```python
async def rewrite_query(question: str) -> str:
    try:
        raw = await _call_llm(REWRITE_SYSTEM, question, max_tokens=300)
        cleaned = _clean_rewrite(raw, question)
        flow_log("query_transform.rewrite_completed", raw=raw, cleaned=cleaned)
        return cleaned
    except Exception:  # noqa: BLE001 - deliberate graceful degradation
        flow_log("query_transform.rewrite_failed", question=question)
        return question
```

A bare `except Exception` is normally a smell. Here it is the correct
behaviour and is annotated as deliberate: a rewriter outage — network error,
rate limit, malformed provider response — should **degrade retrieval quality,
never break the request**. The user still gets an answer, just from an
untransformed query, and `flow_log` records that the transform failed.

### 11.7 Cost

Both techniques add one LLM call **before** retrieval: more latency, more
spend, on every single query. That is the trade being measured — and on this
corpus (§18) neither earned its cost.


---

## 12. Cross-Encoder Reranking

`backend/app/services/reranker.py`

### 12.1 Bi-encoder vs cross-encoder

The dense search uses a **bi-encoder**: the question and each chunk are
embedded *separately* into vectors, then compared with cosine similarity.

```
    question --> [encoder] --> vec_q  \
                                        cosine  --> score
    chunk    --> [encoder] --> vec_d  /
```

That separation is why it is fast enough to search a whole corpus — the chunk
vectors were computed once at ingest time and just sit in the index.

The cost of that speed is that **the model never sees the question and the
chunk together**. It cannot notice "this chunk mentions the exact order type
the question asked about"; it only ever compared two independent summaries.

A **cross-encoder** concatenates them and runs the pair through the model:

```
    [question] [SEP] [chunk] --> [transformer] --> relevance score
```

The model attends across both texts at once, so it is markedly more accurate.
It is also far too slow to score an entire corpus — which is exactly why it
goes **second**.

### 12.2 The two-stage shape

```
cheap recall                          expensive precision
(get the right chunk into the top 20) → (get it into the top 3)

  dense / hybrid search                  cross-encoder
  25 or 25,000 chunks → 20 candidates    20 candidates → reordered
```

This is the standard retrieve-then-rerank pipeline. The economics: scoring 20
pairs with a cross-encoder is affordable per query; scoring 25,000 is not.

### 12.3 Lazy model loading

```python
_model = None
_load_lock = threading.Lock()
_load_error: str | None = None


def _get_model():
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
        except Exception as e:
            _load_error = (
                f"Could not load rerank model: {e}. "
                "First use downloads the model, so this needs network access."
            )
            raise RuntimeError(_load_error) from e
```

Four things this achieves:

1. **The app boots without the model.** The ~90 MB download happens on the
   first reranked query, not at import. A machine that has never downloaded it
   can still run the entire baseline.
2. **Double-checked locking** — the `if _model is not None` check inside the
   lock prevents two concurrent first-requests from both downloading.
3. **The failure is cached** in `_load_error`. Without this, every subsequent
   request would retry a download that is going to fail again, and each retry
   blocks for the full network timeout.
4. **The import is inside the function**, so `sentence_transformers` is not
   even imported unless reranking is used.

### 12.4 Scoring

```python
def rerank(question: str, candidates: list[dict], top_k: int) -> list[dict]:
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
```

`model.predict(pairs)` batches all 20 pairs in a single forward pass.

**Every chunk keeps its original retriever score** under `pre_rerank_score`
while `score` is overwritten with the new one. The inspection UI can therefore
show *both*, which is how you see that a chunk went from RRF rank 7 to
reranked rank 1.

### 12.5 Integration and failure handling

```python
if do_rerank and candidates:
    t0 = time.perf_counter()
    try:
        pool = candidates[: settings.rerank_candidates]
        reranked = reranker.rerank(question, pool, top_k=len(pool))
        ...
        before_ids = [c["id"] for c in pool[:top_k]]
        after_ids  = [c["id"] for c in reranked[:top_k]]
        trace["stages"].append({
            "stage": "rerank",
            "model": settings.rerank_model,
            "candidates_scored": len(pool),
            "top_k_before": before_ids,
            "top_k_after": after_ids,
            "changed_top_k": before_ids != after_ids,
            "promoted_into_top_k": [i for i in after_ids if i not in before_ids],
            "top": _summarize(reranked, 5),
        })
        candidates = reranked
    except RuntimeError as e:
        flow_log("retrieval.rerank_skipped", error=str(e))
        trace["stages"].append({"stage": "rerank", "skipped": True, "reason": str(e)})
```

Note `rerank(..., top_k=len(pool))` — reranking returns the **whole** reordered
pool, not just the top k. Truncation to `top_k` happens once, at the end of
`retrieve()`, so that a subsequent MMR stage still has a full candidate list to
work with.

`promoted_into_top_k` is direct evidence the reranker did something: chunk ids
that were outside the top k before and inside it after.

A model-load failure is caught, recorded in the trace as a skipped stage, and
the pipeline continues with the unreranked ordering.

### 12.6 What reranking can and cannot fix

**Can fix:** a correct chunk that retrieval found but ranked 7th.

**Cannot fix:** a correct chunk retrieval never found. A reranker only
reorders what stage 2 handed it, so its ceiling is `recall@candidate_k`.

The practical diagnostic:

| recall@20 | hit@3 | Conclusion |
|---|---|---|
| 100% | 60% | Reranking is the correct fix — everything is there, ordered badly |
| 70% | 60% | Fix first-stage retrieval; a reranker cannot invent the missing 30% |

---

## 13. MMR Diversity Filtering

`apply_mmr()` in `backend/app/services/retriever.py`

### 13.1 The problem

Chunks overlap by 150 words by construction (§7.3), and documents repeat
themselves. So the top 3 can easily be three near-copies of the same passage.
You have technically retrieved 3 chunks and actually retrieved **1 fact** —
wasting two thirds of the context window, and often missing the second fact a
multi-part question needed.

### 13.2 The formula

Maximal Marginal Relevance selects greedily. At each step, choose the
candidate maximising:

```
   lambda * relevance(c, query)
     - (1 - lambda) * max_similarity(c, already_selected)
```

A chunk is penalised for resembling something already picked.

| lambda | Behaviour |
|---|---|
| `1.0` | pure relevance — MMR effectively off |
| `0.7` | **default** — mostly relevance, breaks up duplicates |
| `0.0` | pure diversity — ignores the question entirely |

### 13.3 Implementation

```python
ids = [c["id"] for c in candidates]
emb_map = vector_store.get_embeddings(ids)
if not emb_map:
    return candidates[:top_k]          # fail open

# Drop candidates with no embedding rather than scoring them as 0/0.
candidates = [c for c in candidates if c["id"] in emb_map]
if not candidates:
    return []
ids = [c["id"] for c in candidates]

q_emb = vector_store.embed_query(question)
rel = {cid: _cosine(q_emb, emb_map[cid]) for cid in ids}

selected, remaining = [], list(candidates)
while remaining and len(selected) < top_k:
    best_item, best_score = None, None
    for cand in remaining:
        cid, emb = cand["id"], emb_map.get(cid)
        if selected and emb:
            redundancy = max(
                _cosine(emb, emb_map[s["id"]]) for s in selected if s["id"] in emb_map
            )
        else:
            redundancy = 0.0
        mmr_score = lambda_mult * rel[cid] - (1 - lambda_mult) * redundancy
        if best_score is None or mmr_score > best_score:
            best_score, best_item = mmr_score, cand

    item = dict(best_item)
    item["mmr_score"] = round(best_score, 6)
    item["mmr_relevance"] = round(rel[best_item["id"]], 6)
    selected.append(item)
    remaining.remove(best_item)
```

**The dropped-candidate guard is the bug fixed in commit `d40edc4`.** A
candidate missing its embedding cannot be scored for relevance or redundancy.
Treating it as `0/0` would make it look maximally novel (zero redundancy
against everything) and let it jump straight to the top of the selection.
Dropping it is correct.

**Relevance is recomputed in embedding space** rather than reusing the
retriever score, so relevance and the redundancy penalty are on the same scale
and `lambda` means what it says. Mixing an RRF score with a cosine similarity
in the same expression would make `lambda` meaningless.

**The first pick has zero redundancy** by definition, so MMR's first selection
is always the most relevant candidate — MMR never sacrifices the top result.

Complexity is O(top_k × candidates × selected) cosine computations, in pure
Python. At `top_k=3` and 20 candidates that is ~120 dot products — negligible.
At `top_k=20` over 200 candidates it would want numpy.

### 13.4 Why it measures as neutral-to-negative here

MMR scores 0.7867 MRR against the 0.8000 baseline — slightly worse.

**This is expected, not a bug.** MMR optimises for covering *distinct
information*, not for ranking one gold chunk first. 22 of the 25 golden
questions have a single correct page, and a single-gold-chunk metric
structurally cannot reward diversity: promoting a *different* correct-adjacent
chunk into slot 2 looks identical to noise.

MMR pays off on multi-fact questions ("what are the two ERP systems **and**
which module talks to each?"). The golden set has exactly three of those —
q04, q10 and q25 — which is not enough signal to move a corpus-level average.

The honest framing: **MMR is not disproven here, it is untested here.**
Measuring it properly needs a multi-fact evaluation set scored on recall, not
hit-rate.

---

## 14. The Trace Object

Every call to `retrieve()` returns `{"chunks": [...], "trace": {...}}`. The
trace is a first-class return value, not a log line — it reaches the HTTP
response, the UI, and `traces.jsonl`.

### 14.1 Full schema

```json
{
  "original_question": "What happens if disableSecurityCheck is true?",
  "search_query": "What happens if disableSecurityCheck is true?",
  "config": {
    "top_k": 3,
    "hybrid": true,
    "rerank": false,
    "rewrite": false,
    "hyde": false,
    "mmr": false,
    "candidate_k": 20,
    "rrf_k": 60
  },
  "stages": [
    {
      "stage": "query_transform",
      "method": "rewrite",
      "before": "hey so the thing where the rep gets money taken off",
      "after": "rep commission deduction amount item cost",
      "changed": true
    },
    {
      "stage": "dense_search",
      "query": "...",
      "returned": 20,
      "top": [ { "rank": 1, "id": "...", "filename": "...", "page": 5,
                 "score": 0.7213, "preview": "first 120 chars..." } ]
    },
    {
      "stage": "bm25_search",
      "query": "...",
      "query_terms": ["what", "happens", "disablesecuritycheck", "true"],
      "returned": 12,
      "top": [ ... ]
    },
    {
      "stage": "rrf_fusion",
      "rrf_k": 60,
      "fused_count": 24,
      "bm25_only_in_top_k": ["def7d74f..._2"],
      "dense_only_in_top_k": ["b3f816c3..._9"],
      "agreed_in_top_k": ["def7d74f..._5"],
      "top": [ ... ]
    },
    {
      "stage": "rerank",
      "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
      "candidates_scored": 20,
      "top_k_before": ["a_1", "a_2", "a_3"],
      "top_k_after":  ["a_7", "a_1", "a_2"],
      "changed_top_k": true,
      "promoted_into_top_k": ["a_7"],
      "top": [ ... ]
    },
    {
      "stage": "mmr",
      "lambda": 0.7,
      "top_k_before": ["a_1", "a_2", "a_3"],
      "top_k_after":  ["a_1", "a_5", "a_9"],
      "changed_top_k": true
    }
  ],
  "timings_ms": {
    "query_transform": 812.4,
    "dense_search": 41.2,
    "bm25_search": 2.1,
    "fusion": 0.4,
    "rerank": 128.7,
    "mmr": 6.3,
    "total": 991.1
  },
  "final_chunk_ids": ["def7d74f..._2", "def7d74f..._5", "b3f816c3..._9"],
  "retrieval_order_before_rerank": ["def7d74f..._5", "b3f816c3..._9", "def7d74f..._2"],
  "trace_id": "tr_20260905_141233_a91f0c"
}
```

Stages appear only when they ran. A baseline query has exactly one stage
(`dense_search`) and two timing entries.

### 14.2 What each field is for

| Field | Answers the question |
|---|---|
| `original_question` / `search_query` | Did a transform change the probe, and to what? |
| `config` | Which strategies were actually active for *this* request? |
| `stages[].returned` | Did this retriever find anything at all? |
| `stages[].query_terms` | How did the tokenizer actually split the query? (catches dropped `*`) |
| `bm25_only_in_top_k` | Which chunks did keyword search rescue? |
| `agreed_in_top_k` | Where did both retrievers concur? |
| `promoted_into_top_k` | Did the reranker actually change anything? |
| `changed_top_k` | Boolean version of the above, for quick scanning |
| `timings_ms` | Which stage is the latency? |
| `retrieval_order_before_rerank` | The before, for a before/after diff |
| `trace_id` | Correlation key into `traces.jsonl` |

### 14.3 Design constraints

**No full chunk text in stage summaries.** Only 120-character previews via
`_summarize`. A five-stage trace with full text would repeat the same 1000-word
chunks five times.

**Timings are per stage, summed for the total.** This makes the breakdown
internally consistent and immediately shows the dominant cost — invariably the
LLM query transform at ~800ms against ~40ms for dense search, which is the
concrete argument against enabling rewrite by default.

**`trace_id` is injected after logging.** `routes/query.py` calls
`log_interaction_trace()`, receives the persisted record, and back-fills the id
into the trace before responding:

```python
tr = log_interaction_trace(...)
if tr:
    result["trace"]["trace_id"] = tr["trace_id"]
```

So a user reporting a bad answer can quote a trace id that indexes directly
into the persisted JSONL.


---

## 15. Generation Layer

`backend/app/services/llm_client.py`

### 15.1 The system prompt

```python
SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions using only the provided "
    "context from the user's documents. If the answer isn't in the context, "
    "say you don't know. Cite the filename and page number when relevant."
)
```

Three instructions, each load-bearing:

1. **"using only the provided context"** — the anti-hallucination constraint.
   The model is not being asked what it knows; it is being asked what the
   documents say.
2. **"If the answer isn't in the context, say you don't know"** — gives the
   model a licence to refuse. Without an explicit out, models fabricate to
   satisfy the request.
3. **"Cite the filename and page number"** — makes every claim auditable. A
   citation is what lets a user verify the answer against the source in
   seconds.

This constant is imported by `trace_logger.py` and stored **inside every trace
record**, so a trace from an older prompt version replays against the prompt
it actually used, not the current one.

### 15.2 Context assembly

```python
def build_context_block(matches: list[dict]) -> str:
    parts = []
    for m in matches:
        parts.append(f"[{m['filename']} p.{m['page']}]\n{m['text']}")
    return "\n\n---\n\n".join(parts)
```

Each chunk is prefixed with a bracketed citation header and separated by a
horizontal rule:

```
[Advita DOCs.pdf p.5]
Discrepancy penalty: Item Cost x 1.4 deducted from rep commission...

---

[Cim Authentication.pdf p.6]
JWT payload is cached in Redis with TTL capped at 60 minutes...
```

The inline header is what makes citation possible: the model can see which
text came from where without any tool call or structured-output machinery.
The `---` separator is unambiguous — chunk text is prose and does not contain
a bare horizontal rule.

### 15.3 The request

```python
async def generate_answer(question: str, matches: list[dict]) -> str:
    if not settings.llm_api_key:
        key_name = "OPENROUTER_API_KEY" if settings.openrouter_enabled else "GROQ_API_KEY"
        raise RuntimeError(f"{key_name} is not set. Add it to backend/.env")

    context = build_context_block(matches)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(settings.llm_url, json=payload, headers=headers)
        ...
        resp.raise_for_status()
        data = resp.json()
```

**Context precedes the question.** With the context first, the model reads the
evidence before the task — and on providers with prefix caching, a stable
prefix is the cacheable part.

**Missing-key check comes first**, before any work, and names the exact
environment variable to set for the *currently selected* provider.

**60-second timeout** accommodates slow free-tier models without hanging a
request forever.

### 15.4 The 200-with-an-error-body case

```python
choices = data.get("choices")
if not choices:
    # Some providers return 200 with an error body for failure modes
    # (e.g. model unavailable, no credit), so raise_for_status() alone
    # doesn't catch it.
    error = data.get("error", {})
    message = error.get("message") if isinstance(error, dict) else None
    raise RuntimeError(
        f"{settings.llm_provider} returned no choices: {message or data}"
    )

answer = choices[0]["message"]["content"]
```

This was found the hard way. OpenRouter can return **HTTP 200** with
`{"error": {"message": "..."}}` for model-unavailable or insufficient-credit
conditions. `resp.raise_for_status()` passes, `data["choices"][0]` then raises
a bare `KeyError`, and the user sees a 500 with no explanation. The explicit
check turns that into an actionable message.

The `isinstance(error, dict)` guard exists because `error` is sometimes a
string rather than an object, depending on the provider.

### 15.5 Error propagation in the route

`routes/query.py` translates exceptions into meaningful HTTP status codes,
and logs a trace in **both** failure paths:

```python
try:
    answer = await generate_answer(payload.question, matches)
except RuntimeError as e:
    flow_log("llm.error", error=str(e))
    log_interaction_trace(..., answer="", error=str(e))
    raise HTTPException(status_code=400, detail=str(e))
except httpx.HTTPStatusError as e:
    flow_log("llm.error", status_code=e.response.status_code, response=e.response.text)
    log_interaction_trace(..., answer="", error=f"{e.response.status_code} {e.response.text}")
    raise HTTPException(
        status_code=502,
        detail=f"LLM provider request failed: {e.response.status_code} {e.response.text}",
    )
```

| Exception | Status | Meaning |
|---|---|---|
| `RuntimeError` | **400** | Client-side configuration problem — missing key, no choices returned |
| `httpx.HTTPStatusError` | **502** | Upstream provider failed — bad gateway is the honest code |

**Failed generations are traced too.** A trace with `"error"` set and an empty
answer is exactly the record you need when diagnosing an outage after the fact.

### 15.6 Two early-return paths

Before generation is attempted, `query.py` handles two cases:

```python
if not matches:
    answer = "No documents have been uploaded yet, or no relevant content was found."
    # traced, returned with sources=[]

if payload.retrieval_only:
    answer = "(retrieval_only=true — generation skipped)"
    # traced, returned with the retrieved sources
```

`retrieval_only` is the important one: it lets the Inspector and the eval
harness exercise the full retrieval pipeline **without spending an LLM call**.
A 25-question sweep across 7 configurations is 175 retrievals; at zero
generation cost that is free, and it is why the eval harness never calls the
LLM unless triage explicitly asks for an answer.

---

## 16. Trace Logging and Replay

### 16.1 Live logging — `services/trace_logger.py`

Every query — successful, empty, retrieval-only, or errored — appends one JSON
line to `backend/data/traces.jsonl`.

```python
def log_interaction_trace(
    question, chunks, answer,
    trace_info=None, config=None, model=None, model_params=None,
    prompt_version="v1.0.0", system_prompt=SYSTEM_PROMPT,
    trace_id=None, error=None,
) -> dict[str, Any] | None:
    if not settings.trace_logging_enabled:
        return None
    try:
        now = datetime.now(timezone.utc)
        tid = trace_id or f"tr_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        ...
        with _lock:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
    except Exception as e:
        flow_log("trace.log_error", error=str(e))
        return None
```

Design points:

- **A module-level `threading.Lock`** serialises appends. Concurrent requests
  writing to the same file would otherwise interleave partial lines and
  corrupt the JSONL.
- **The entire function is wrapped in try/except returning `None`.** Trace
  logging is observability, not product behaviour. A full disk must not break
  the user's query. The failure is itself logged via `flow_log`.
- **Score is resolved with a fallback chain** so a chunk always reports
  *something* comparable regardless of which stage produced it:

  ```python
  score = c.get("score")
  if score is None: score = c.get("rrf_score")
  if score is None: score = c.get("rerank_score")
  ```

- **`prompt_version` and the full `system_prompt` text are stored per record.**
  Without them, a trace from three prompt revisions ago replays against the
  wrong prompt and the replay is a lie.
- **Path resolution handles both working directories** — running from
  `backend/` and running from the repo root both resolve to the same file:

  ```python
  def get_traces_file_path() -> str:
      raw_path = settings.traces_path
      if os.path.isabs(raw_path):
          return raw_path
      if os.path.exists(raw_path) or os.path.exists(os.path.dirname(raw_path) or "."):
          return os.path.abspath(raw_path)
      backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
      return os.path.abspath(os.path.join(backend_root, raw_path))
  ```

### 16.2 The trace record schema

```json
{
  "trace_id": "tr_20260905_141233_a91f0c",
  "timestamp": "2026-09-05T14:12:33.481920+00:00",
  "original_question": "How do I initialize the AuthClient in v3?",
  "prompt_version": "v1.0.0",
  "system_prompt": "You are a helpful assistant answering questions using only...",
  "model": "openai/gpt-oss-20b",
  "model_params": { "temperature": 0.0, "max_tokens": 1024, "top_p": 1.0 },
  "config": { "top_k": 3, "hybrid": true, "rerank": false,
              "rewrite": false, "mmr": false, "hyde": false,
              "retrieval_only": false },
  "retrieved_chunks": [
    { "id": "cim_auth_p2_c1", "filename": "Cim Authentication v2.pdf",
      "page": 2, "score": 0.88, "text": "AuthClient initialization (v2.4)..." }
  ],
  "raw_output": "To initialize the AuthClient, use ...",
  "answer": "To initialize the AuthClient, use ...",
  "stages": [ ... ],
  "timings_ms": { ... }
}
```

**Full chunk `text` is stored**, not a preview. This is the deliberate
difference between the *stage* trace (previews, for size) and the *interaction*
trace (full text, for replay). Replay is impossible without the exact context
the model saw.

### 16.3 The current dataset

`backend/data/traces.jsonl` holds **104 records**:

| Source | Count | Distinguishing field |
|---|---:|---|
| Generated by `eval/generate_traces.py` | 100 | has `expected_mode` and `is_demo` |
| Logged live by `trace_logger.py` | 4 | no `expected_mode` |

Both share the same schema for the fields replay depends on, which is the
point — the generated corpus is a stand-in for production volume, not a
different format.

### 16.4 The generator — `eval/generate_traces.py`

Produces 100 developer-documentation traces across five seeded failure modes,
with `random.seed(42)` so the dataset is byte-identical on every regeneration.

```python
mode_distribution = (
    ["v2_signature_returned_for_v3_query"]      * 30 +
    ["omitted_prerequisite_header_or_import"]   * 25 +
    ["wildcard_and_special_char_token_dropped"] * 20 +
    ["numeric_status_code_confusion"]           * 15 +
    ["partial_multihop_context_truncation"]     * 10
)
random.shuffle(mode_distribution)
```

Ten trace indices are marked `is_demo: True`:

```python
demo_indices = {1, 5, 12, 18, 25, 34, 45, 56, 78, 90}
```

These represent the "curated demo set" a team would show in a weekly review —
and the whole point of marking them is to measure how the demo set's failure
profile differs from a random sample of real traffic (§19.4).

Each mode has 3–5 question templates carrying a realistic failure: a v2
signature returned for a v3 question, an endpoint given without its required
header, a question about `*` answered without mentioning `*`, and so on.

### 16.5 The replay engine — `eval/replay_trace.py`

```bash
.venv/Scripts/python.exe eval/replay_trace.py --sample --seed 20260901
.venv/Scripts/python.exe eval/replay_trace.py --replay tr_042
```

**Seeded sampling** draws 20 random non-demo traces plus the 10 demo traces:

```python
def draw_seeded_samples(seed: int = 20260901) -> dict:
    traces = load_all_traces()
    random.seed(seed)
    non_demo_traces = [t for t in traces if not t.get("is_demo")]
    demo_traces     = [t for t in traces if t.get("is_demo")]
    sample_20 = random.sample(non_demo_traces, 20)
    sample_demo_10 = demo_traces[:10] if len(demo_traces) >= 10 else random.sample(traces, 10)
    ...
```

The seed is recorded in `notes.md`, so the exact 20 traces that were
open-coded can be redrawn by anyone at any time. This is what makes the
qualitative analysis auditable rather than anecdotal.

**Replay** reconstructs the exact prompt from the trace record alone — nothing
is read from the live index or the current config:

```python
system_prompt = target.get("system_prompt", "You are a helpful assistant...")
chunks = target.get("retrieved_chunks", [])

context_parts = [f"[{c['filename']} p.{c['page']}]\n{c['text']}" for c in chunks]
context_block = "\n\n---\n\n".join(context_parts)

reconstructed_user_prompt = (
    f"Context:\n{context_block}\n\nQuestion: {target['original_question']}"
)
```

This is deliberately the *same* assembly logic as
`llm_client.build_context_block()`. If the two ever diverge, replay stops
being faithful — which is a known duplication worth consolidating (§24).

**Schema audit** runs on every replay:

```python
expected_fields = [
    "trace_id", "timestamp", "original_question", "prompt_version",
    "system_prompt", "model", "model_params", "config",
    "retrieved_chunks", "raw_output", "answer",
]
present_fields = [f for f in expected_fields if f in target and target[f] is not None]
missing_fields = [f for f in expected_fields if f not in target or target[f] is None]
```

Documented reconstruction limits, carried in the replay output itself:

> Added explicit `prompt_version`, `system_prompt`, `model_params`, and chunk
> text metadata to enforce 100% replayability. External API network latency
> (`timings_ms`) and provider server timestamps could not be reconstructed
> from the static trace alone.

At `temperature = 0.0` the replayed output matches the original exactly
(`"match": true`), which is what the audit demonstrates.

---

## 17. Evaluation System

### 17.1 Metrics — `services/metrics.py`

Three metrics that answer three different questions. Reporting the wrong one
is the single most common way a retrieval writeup goes wrong.

| Metric | Question it answers |
|---|---|
| **hit-rate@k** | Did *at least one* correct chunk appear in the top k? Binary per question, then averaged. |
| **recall@k** | What *fraction* of all correct chunks appeared in the top k? |
| **MRR** | How *high* did the first correct chunk rank? `1/rank`, averaged. |

**hit-rate@k** is the headline. It is the right metric when the user only
needs one correct chunk to get a good answer — the normal case for Q&A.

**recall@k** matters when a question needs several pages. `hit-rate@3 = 1.0`
with `recall@3 = 0.5` means you found one of the two pages required — the
answer will be half right, and hit-rate will not tell you.

**MRR** is sensitive where hit-rate is blind. Moving the gold chunk from rank
3 to rank 1 leaves `hit-rate@3` unchanged but lifts MRR from 0.33 to 1.0. This
is exactly the difference between hybrid and rerank in the measured results.

**Why track all three:** a change can raise hit-rate@3 while lowering MRR (it
drags more gold chunks in but ranks them worse). Reporting only the flattering
number is how people fool themselves.

### 17.2 Key normalisation

```python
def _page_key(filename: str | None, page) -> tuple:
    fn = (filename or "").strip().lower()
    try:
        pg = int(page)
    except (TypeError, ValueError):
        pg = page
    return (fn, pg)
```

Metadata round-trips through JSON and SQLite, so `page` can come back as `int`
or `str`, and filenames vary in surrounding whitespace and case. Without this
normalisation, `("Advita DOCs.pdf", 5)` and `("advita docs.pdf", "5")` would
be different keys and every hit would be silently missed.

### 17.3 Metric implementations

```python
def hit_at_k(chunks, expected, k) -> bool:
    want = expected_keys(expected)
    got = retrieved_keys(chunks)[:k]
    return any(g in want for g in got)


def recall_at_k(chunks, expected, k) -> float:
    want = expected_keys(expected)
    if not want:
        return 0.0
    got = set(retrieved_keys(chunks)[:k])
    return len(want & got) / len(want)


def first_hit_rank(chunks, expected) -> int | None:
    want = expected_keys(expected)
    for i, g in enumerate(retrieved_keys(chunks), start=1):
        if g in want:
            return i
    return None


def reciprocal_rank(chunks, expected) -> float:
    rank = first_hit_rank(chunks, expected)
    return (1.0 / rank) if rank else 0.0
```

Note `first_hit_rank` scans the **full** result list, not just the top k — so
MRR can distinguish "found at rank 5" from "never found", which hit-rate@3
collapses into the same bucket.

### 17.4 Aggregation

```python
def aggregate(per_question, k_values) -> dict:
    n = len(per_question)
    if n == 0:
        return {"n": 0}
    out = {"n": n}
    for k in k_values:
        hits = sum(1 for r in per_question if hit_at_k(r["chunks"], r["expected"], k))
        recalls = [recall_at_k(r["chunks"], r["expected"], k) for r in per_question]
        out[f"hit_rate@{k}"] = round(hits / n, 4)
        out[f"recall@{k}"]   = round(sum(recalls) / n, 4)
    rrs = [reciprocal_rank(r["chunks"], r["expected"]) for r in per_question]
    out["mrr"] = round(sum(rrs) / n, 4)
    out["never_found"] = sum(1 for r in rrs if r == 0.0)
    return out
```

`never_found` counts questions where the correct page appeared **nowhere** in
the results. That is a categorically different problem from "ranked 5th" and
deserves its own number.

### 17.5 Category breakdown

```python
def aggregate_by_category(per_question, k) -> dict:
    buckets: dict[str, list[dict]] = {}
    for r in per_question:
        buckets.setdefault(r.get("category") or "uncategorised", []).append(r)
    out = {}
    for cat, rows in sorted(buckets.items()):
        hits = sum(1 for r in rows if hit_at_k(r["chunks"], r["expected"], k))
        out[cat] = {"n": len(rows), "hits": hits, f"hit_rate@{k}": round(hits / len(rows), 4)}
    return out
```

This is the breakdown that answers *"which failures did my change NOT fix?"* —
a corpus-wide average hides that hybrid fixed every `exact_term` question and
did nothing for the `vague_phrasing` ones.

### 17.6 The golden set — `eval/golden_set.json`

25 questions, each recording which page(s) actually contain the answer.

```json
{
  "id": "q01",
  "question": "What does BILL-RESTOCK mean?",
  "expected": [{ "filename": "Advita DOCs.pdf", "page": 2 }],
  "category": "exact_term",
  "note": "Dense search confuses BILL-RESTOCK / BILL-ONLY / RESTOCK-ONLY because they embed almost identically. BM25 should nail it on the literal token.",
  "failure_kind": "unlabeled"
}
```

**Category distribution:**

| Category | n | Why these questions are hard |
|---|---:|---|
| `exact_term` | 11 | Rare literal identifiers that embeddings blur together |
| `semantic` | 6 | Conceptual questions with no shared vocabulary |
| `specific_fact` | 4 | The right page is not enough; a number must survive into the answer |
| `vague_phrasing` | 3 | Conversational, filler-heavy, no domain terms |
| `multi_hop` | 1 | Needs facts from more than one page |

**`failure_kind`** is a manual label applied after inspecting a trace:

| Value | Meaning | Fix |
|---|---|---|
| `retrieval` | The right page never made the top k | Fix retrieval |
| `generation` | The right page **was** retrieved, answer still wrong | Fix the prompt, chunk size, or model |
| `ok` | Works fine — kept as a regression guard | — |
| `unlabeled` | Not yet triaged | — |

**Ground truth is `(filename, page)`, never chunk id.** Chunk ids
(`doc_id_N`) regenerate every time a PDF is re-uploaded; filename + page
survives re-ingestion. This decision is what keeps the golden set usable
across corpus rebuilds.

### 17.7 The second golden set — `eval/golden_set.jsonl`

A 12-question subset used as the Week 4 submission set, in JSONL rather than
JSON, and carrying an extra `expected_chunk_id` field:

```json
{"id":"q01","question":"What does BILL-RESTOCK mean?","category":"exact_term",
 "expected_chunk_id":"b3f816c32b0b46c1bf5520e689f981d8_1",
 "expected":[{"filename":"Advita DOCs.pdf","page":2}]}
```

Ids: q01, q02, q03, q06, q08, q09, q12, q13, q15, q17, q18, q20 — weighted
towards `exact_term` (8 of 12) because that submission needed at least four
questions containing exact identifiers.

`expected_chunk_id` records the id **as it existed at the time of that
measurement**, for auditability. It is a snapshot, not the matching key — the
matching key is still filename + page.


### 17.8 The configuration matrix — `eval/run_eval.py`

```python
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
```

**Every configuration differs from `baseline` in exactly one dimension** — with
two deliberate exceptions, both labelled as such:

- `hybrid_rerank` — a stacking check: does combining two winners compound?
- `everything` — a ceiling check. The description says explicitly it is *not*
  a valid single change. Its purpose is to show the best achievable number, so
  you know how much headroom remains.

The `_desc` prefix convention keeps metadata out of the flag payload:

```python
cfg = {k: v for k, v in CONFIGS[name].items() if not k.startswith("_")}
result = await retriever.retrieve(q["question"], top_k=top_k, **cfg)
```

Flags are splatted straight into `retrieve()`. Adding a config is a dict entry
and nothing else.

### 17.9 Running one configuration

```python
async def run_config(name, questions, top_k, only_question=None) -> dict:
    cfg = {k: v for k, v in CONFIGS[name].items() if not k.startswith("_")}
    rows = []
    for q in questions:
        if only_question and q["id"] != only_question:
            continue
        result = await retriever.retrieve(q["question"], top_k=top_k, **cfg)
        chunks = result["chunks"]
        rank = metrics.first_hit_rank(chunks, q["expected"])
        rows.append({
            "id": q["id"], "question": q["question"], "category": q.get("category"),
            "expected": q["expected"],
            "chunks": [ {"rank": c.get("rank"), "filename": c.get("filename"),
                         "page": c.get("page"),
                         "score": round(c["score"], 4) if c.get("score") is not None else None,
                         "id": c.get("id")} for c in chunks ],
            "first_hit_rank": rank,
            f"hit@{HEADLINE_K}": metrics.hit_at_k(chunks, q["expected"], HEADLINE_K),
            "reciprocal_rank": round(metrics.reciprocal_rank(chunks, q["expected"]), 4),
            "trace": result["trace"],
        })
    return {
        "config_name": name, "config": cfg, "description": CONFIGS[name]["_desc"],
        "top_k": top_k,
        "overall": metrics.aggregate(rows, K_VALUES),
        "by_category": metrics.aggregate_by_category(rows, HEADLINE_K),
        "questions": rows,
    }
```

**The full trace for every question is retained in the saved result.** A saved
run is therefore not just a score — it is a complete forensic record. Six
months later you can open `results/hybrid.json` and see exactly which chunks
came back for q15 and why.

**Chunk text is stripped** from the saved rows (only rank/filename/page/score/id
are kept), which keeps result files at tens of KB instead of megabytes.

### 17.10 CLI

```bash
cd backend

# One configuration, saved for later comparison
.venv/Scripts/python -m eval.run_eval --config baseline --save
.venv/Scripts/python -m eval.run_eval --config hybrid   --save
.venv/Scripts/python -m eval.run_eval --config rerank   --save

# The before/after table — the actual deliverable
.venv/Scripts/python -m eval.run_eval --compare baseline rerank

# Every configuration, ranked as a leaderboard
.venv/Scripts/python -m eval.run_eval --sweep --save

# Drill into one question with every retrieved chunk printed
.venv/Scripts/python -m eval.run_eval --config hybrid --question q15 --verbose

# What configurations exist
.venv/Scripts/python -m eval.run_eval --list-configs
```

| Flag | Effect |
|---|---|
| `--config NAME` | Run one named configuration |
| `--compare BEFORE AFTER` | Load two saved runs and print the delta table |
| `--sweep` | Run every configuration, print a leaderboard |
| `--question ID` | Restrict to one question (implies partial run — refuses to `--save`) |
| `--top-k N` | Retrieval depth (default 3) |
| `--save` | Write to `eval/results/<config>.json` |
| `--verbose` | Print every retrieved chunk with HIT markers |
| `--list-configs` | Print names, descriptions, flags |

The harness bootstraps its own import path and refuses to run on an empty
index:

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
...
n = retriever.ensure_bm25_index(force=True)
print(f"\nBM25 index built over {n} chunks.")
if n == 0:
    raise SystemExit("No chunks in the vector store — upload your PDFs first.")
```

`--question` plus `--save` is explicitly refused, because a partial run would
overwrite a full result file with a one-question one:

```python
if args.save and not args.question:
    print(f"  saved -> {save_run(run)}\n")
elif args.save:
    print("  not saved (partial run: --question was set)\n")
```

### 17.11 The comparison report

`print_comparison()` is the deliverable-shaped output. It prints:

1. **Metric deltas** — hit@1/3/5, recall@1/3/5, MRR, each with an
   UP/DOWN/same arrow and a signed delta.
2. **Category deltas** — flagged `<-- FIXED` or `<-- REGRESSED`.
3. **Per-question movement**, computed by set difference on `hit@3`:

```python
fixed, broke, still = [], [], []
for qid in sorted(set(bq) & set(aq)):
    was, now = bq[qid][hk], aq[qid][hk]
    if   not was and now: fixed.append(qid)
    elif was and not now: broke.append(qid)
    elif not was and not now: still.append(qid)
```

- **FIXED** — questions the change repaired
- **BROKEN** — regressions the change introduced
- **STILL BROKEN** — *"what did your change NOT fix?"*

That third list is the one that matters most and the one people omit. It is
printed unconditionally, with the question text, so it cannot be quietly
skipped.

### 17.12 Evaluation over HTTP — `routes/evaluation.py`

The same harness is exposed to the UI. The route imports the CLI module
lazily, adjusting `sys.path` so `eval` is importable from inside the app:

```python
def _load_eval_module():
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from eval.run_eval import CONFIGS, load_golden, run_config
    return CONFIGS, load_golden, run_config
```

`POST /api/evaluate` validates the config name, forces a BM25 rebuild so the
run starts from a known index state, and returns the full run:

```python
@router.post("/evaluate", response_model=EvalResponse)
async def evaluate(payload: EvalRequest):
    configs, load_golden, run_config = _load_eval_module()
    if payload.config not in configs:
        raise HTTPException(400, f"Unknown config '{payload.config}'. Available: {', '.join(configs)}")
    questions = load_golden()
    retriever.ensure_bm25_index(force=True)
    run = await run_config(payload.config, questions, payload.top_k or settings.top_k)
    return EvalResponse(**run)
```

### 17.13 Triage — the retrieval-vs-generation classifier

`POST /api/triage` is the mechanical version of the question this project is
built around.

```python
hit             = metrics.hit_at_k(chunks, expected, top_k)
rank            = metrics.first_hit_rank(chunks, expected)
recall          = metrics.recall_at_k(chunks, expected, top_k)
reciprocal_rank = metrics.reciprocal_rank(chunks, expected)

if not hit:
    verdict = "retrieval_failure"
    reasoning = (f"RETRIEVAL FAILURE. None of the expected pages ({expected_pages}) appeared "
                 f"in the top {top_k}. Retrieved instead: {retrieved_pages}.")
elif rank and rank > 1 and recall < 1.0:
    verdict = "partial_retrieval"
    reasoning = (f"PARTIAL RETRIEVAL. A correct page was found at rank {rank}, but only "
                 f"{recall:.0%} of expected pages made the top {top_k}.")
else:
    verdict = "generation_candidate"
    reasoning = (f"RETRIEVAL SUCCEEDED. The expected page was at rank {rank}, and "
                 f"{recall:.0%} of expected pages were in the top {top_k}.")
```

| Verdict | Condition | What to fix |
|---|---|---|
| `retrieval_failure` | No expected page in the top k | Hybrid search, reranking, chunking — **not** the model |
| `partial_retrieval` | Some but not all expected pages present | Increase k, or fix multi-hop retrieval |
| `generation_candidate` | Retrieval did its job | The prompt, the chunk size, or the model |

The reasoning string names the expected pages and what was retrieved instead,
so the verdict is self-evidencing rather than a bare label.

`generate: bool = True` on the request controls whether an answer is also
produced. When retrieval already failed, generating an answer costs a call to
confirm what the verdict already established — so the Inspector passes
`generate: !retrievalOnly`.

---

## 18. Measured Results

Corpus: `Advita DOCs.pdf` + `Cim Authentication.pdf`, 25 chunks.
Questions: 25. `top_k = 3`, `rrf_k = 60`, `candidate_k = 20`,
embedding model `all-MiniLM-L6-v2`. Saved runs in `backend/eval/results/`.

### 18.1 Baseline — what was actually broken

```
hit-rate@1  72.0%      recall@1  66.0%
hit-rate@3  88.0%      recall@3  84.0%
hit-rate@5  88.0%      recall@5  84.0%
MRR         0.8000     never found at all: 3 / 25
```

`hit@3 == hit@5` is itself a finding: nothing was sitting at rank 4 or 5
waiting to be picked up by a larger k. The three failures were **total**
misses, not near misses — and the triage endpoint classified all three as
retrieval failures.

| id | question | wanted | got instead |
|---|---|---|---|
| q01 | What does `BILL-RESTOCK` mean? | Advita p.2 | p.14, p.6, p.10 |
| q15 | What happens if `disableSecurityCheck` is true? | CimAuth p.6 | p.5, p.7, p.10 |
| q18 | How does user impersonation work? | CimAuth p.3 | p.10, p.7, p.8 |

**Three retrieval failures, zero generation failures.** This is why "just use a
bigger model" would have been wasted money: the answer text was never in the
context window at all.

### 18.2 Full leaderboard

| config | hit@1 | hit@3 | hit@5 | recall@3 | MRR | never found |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 72.0% | 88.0% | 88.0% | 84.0% | 0.8000 | 3 |
| **hybrid** | 80.0% | **96.0%** | **96.0%** | 90.0% | 0.8733 | 1 |
| **rerank** | **88.0%** | **96.0%** | **96.0%** | **92.0%** | **0.9200** | 1 |
| hybrid_rerank | **88.0%** | **96.0%** | **96.0%** | **92.0%** | **0.9200** | 1 |
| rewrite | 68.0% | 88.0% | 88.0% | 84.0% | 0.7800 | 3 |
| hyde | 72.0% | 88.0% | 88.0% | 84.0% | 0.8000 | 3 |
| mmr | 72.0% | 88.0% | 88.0% | 82.0% | 0.7867 | 3 |

### 18.3 Reading the table

**The headline: hit-rate@3 goes 88.0% → 96.0%, +8 percentage points, from one
change.**

**Two configs tie on hit@3, and hit@3 alone cannot choose between them.** This
is exactly why three metrics are tracked:

| | hybrid | rerank |
|---|---:|---:|
| hit@3 | 96.0% | 96.0% |
| hit@1 | 80.0% | **88.0%** |
| recall@3 | 90.0% | **92.0%** |
| MRR | 0.8733 | **0.9200** |

Same number of right answers in the top 3 — but **reranking puts them first**.
If the UI shows one chunk, or the prompt weights the first chunk most heavily,
that difference is the whole product.

**`hybrid_rerank` is byte-identical to `rerank` on every metric.** Stacking
bought nothing. The plausible reading: the cross-encoder is strong enough to
find the right ordering from the dense candidate pool alone, so BM25's
contribution to the *pool* is redundant once reranking is applied. Whether
that generalises beyond a 25-chunk corpus is untested — but the honest
statement is that **on this corpus, adding hybrid to rerank costs latency and
buys zero measured improvement.**

**Category breakdown, baseline → hybrid:**

| category | n | baseline | hybrid | rerank |
|---|---:|---:|---:|---:|
| exact_term | 11 | 81.8% (9) | 90.9% (10) | 90.9% (10) |
| semantic | 6 | 83.3% (5) | **100%** (6) | **100%** (6) |
| specific_fact | 4 | 100% (4) | 100% (4) | 100% (4) |
| vague_phrasing | 3 | 100% (3) | 100% (3) | 100% (3) |
| multi_hop | 1 | 100% (1) | 100% (1) | 100% (1) |

The `semantic` category going to 100% is mildly counter-intuitive — BM25 is
supposed to help `exact_term`, not `semantic`. The explanation is that the
category label describes *why the question is hard*, not which retriever
should win it; q15's `disableSecurityCheck` is a semantic-sounding question
whose answer hinges on a literal identifier.

### 18.4 Why hybrid worked — the q15 evidence

For *"What happens if `disableSecurityCheck` is true?"*:

```
dense  ranked the correct page (CimAuth p.6) at #4   <- missed at k=3
bm25   ranked the correct page at #1                 <- exact identifier match
RRF    fused them -> correct page at #1              <- FIXED
```

The UI badge reads `dense #4 | bm25 #1`. That one line is the proof: keyword
search found what semantic search missed, because `disableSecurityCheck` is a
rare literal token, and BM25 weights rare tokens heavily while an embedding
model blurs them into "security config stuff".

### 18.5 What the change did NOT fix

**q01 — "What does `BILL-RESTOCK` mean?" fails in every single configuration.**
This is the most instructive result in the project.

BM25 *does* rank the correct page (p.2) at **#1**. It still loses:

```
dense top-5:  p.14  p.6   p.10  p.5   p.3      <- p.2 not in the top 20 at all
bm25  top-5:  p.2   p.14  p.13  p.5   p.6      <- p.2 is #1
fused:        p.14  p.6   p.5   p.13  p.3      <- p.2 lost
```

**Why.** `BILL-RESTOCK` appears in 5 of 25 chunks, so its IDF is only
moderate — no single chunk dominates. Meanwhile p.14 is ranked #1 by dense
**and** #2 by BM25, so RRF rewards it for **agreement**. p.2 gets one
contribution (1/61); p.14 gets two (1/61 + 1/62).

RRF is working exactly as designed. Rewarding agreement is the feature. Here
the feature costs the answer.

**Was it just bad tuning?** No — measured directly:

| rrf_k | 1 | 5 | 10 | 20 | 60 |
|---|---:|---:|---:|---:|---:|
| hit@3 | 96% | 92% | 96% | 96% | 96% |

Flat. No fusion constant rescues q01, because **dense search never surfaces
p.2 at all**, so fusion has only one vote to work with. Reranking cannot fix
it either — a reranker only reorders candidates retrieval already found.

**The real fix for q01 is chunking, not retrieval.** The definition of
`BILL-RESTOCK` sits in a wide table split across pages 2–3, so the row label
and its meaning land in different chunks. A failure that *looks* like
retrieval and is actually upstream of it. This is the finding that motivated
building the Chunks Explorer (§21.6) — so chunk boundaries can be inspected
directly rather than inferred.

### 18.6 The techniques that did not earn their cost

**Query rewriting made things worse.** MRR 0.8000 → 0.7800, hit@1 72% → 68%.
Paraphrasing destroys the exact identifiers these questions depend on. Real
latency cost (~800ms per query), real spend, zero benefit on this corpus.

**HyDE was exactly neutral.** Identical to baseline on every metric. The
hypothetical passage landed in the same vector neighbourhood the raw question
already reached. It costs an LLM call to achieve nothing here.

**MMR slightly hurt.** MRR 0.8000 → 0.7867, recall@3 84% → 82%. Expected, and
explained in §13.4: 22 of 25 questions have a single correct page, and a
single-gold-chunk metric cannot reward diversity.

**Tokenisation gaps remain.** `*` and `-L` (q20, q04) tokenise poorly.
`tokenize("wildcard * permission")` drops the `*` entirely, which is visible in
the inspector's `query_terms` line.

### 18.7 The Week 4 submission measurement

[results.md](results.md) records a separate, narrower measurement on the
12-question `golden_set.jsonl` with per-question latency:

| Run | Hits / 12 | Hit-rate@3 | p50 latency |
|---|---:|---:|---:|
| Baseline: dense | 9/12 | 75.0% | 123.17 ms |
| After: hybrid + RRF | 11/12 | 91.7% | 120.34 ms |
| Delta | +2 | **+16.7 pp** | −2.83 ms |

The latency delta is reported honestly as noise, not as a win: a second warmed
pass produced 143.89 ms and 144.32 ms respectively while reproducing the exact
same 9/12 and 11/12 hit counts. **The variance between passes exceeds the
difference between configurations**, so the shipping decision treats latency
as neutral.

Per-question movement on that set: q15 and q18 fixed, q01 still broken, no
regressions among the nine baseline hits.

**Shipping decision: hybrid + RRF was shipped**, by flipping
`hybrid_enabled` to `True` in `config.py`. One flag, one behaviour change,
fully reversible, with the baseline still reproducible through the harness.


---

## 19. Error Analysis Workflow

Week 5 moved from *"is retrieval working?"* to *"what does it actually get
wrong, in what proportions, and which failure should we fix first?"*

### 19.1 The method

```
1. Generate / collect 100 interaction traces        generate_traces.py
2. Draw a SEEDED random sample of 20                replay_trace.py --sample
3. Replay one trace end-to-end, audit the schema    replay_trace.py --replay
4. Open-code all 20 in one verbatim sentence each   notes.md §3
5. Cluster the sentences into failure modes         taxonomy.md
6. Count, rank by frequency × severity              taxonomy.md
7. Compare the demo set against the random sample   notes.md §4
8. Write a DATED, FALSIFIABLE prediction            prediction.md
```

Two properties make this auditable rather than anecdotal:

- **The sample is seeded** (`20260901`) and the seed is published, so the exact
  20 traces can be redrawn by anyone.
- **The prediction is dated and falsifiable**, and pinned to a git commit hash.

### 19.2 The taxonomy

From `taxonomy.md`, over the 20-trace random sample:

| Mode | Count | Freq | Severity | Example |
|---|---:|---:|---|---|
| `v2_signature_returned_for_v3_query` | 7 | 35.0% | Ships broken code to user repo | `tr_042` |
| `omitted_prerequisite_header_or_import` | 4 | 20.0% | Ships broken code to user repo | `tr_050` |
| `wildcard_and_special_char_token_dropped` | 4 | 20.0% | Merely annoys the reader | `tr_048` |
| `numeric_status_code_confusion` | 3 | 15.0% | Merely annoys the reader | `tr_067` |
| `partial_multihop_context_truncation` | 2 | 10.0% | Merely annoys the reader | `tr_097` |

**Severity is binary and behavioural**, not a 1–5 scale: does this failure
cause the user to ship broken code, or does it just annoy them? The two
top modes together — **55% of all failures** — put non-compiling code into
developer environments.

Note the third mode, `wildcard_and_special_char_token_dropped`, is the same
root cause as the tokenizer limitation measured in §18.6 — the taxonomy
independently rediscovered a known code-level gap from production-shaped
traces, which is a reassuring cross-check on the method.

### 19.3 Replay evidence

`tr_042`, replayed offline from the trace record alone:

```json
{
  "trace_id": "tr_042",
  "original_question": "How do I call `getBackorders()` in SDK v3?",
  "prompt_version": "v1.0.0",
  "model": "llama-3.3-70b-versatile",
  "model_params": { "temperature": 0.0, "max_tokens": 1024, "top_p": 1.0 },
  "reconstructed_user_prompt":
    "Context:\n[Advita FE.pdf p.3]\ngetBackorders(agencyId)\n\nQuestion: How do I call `getBackorders()` in SDK v3?",
  "original_output": "`getBackorders` accepts single agencyId parameter [Advita FE.pdf p.3]",
  "replayed_output": "`getBackorders` accepts single agencyId parameter [Advita FE.pdf p.3]",
  "match": true
}
```

**Schema audit outcome.** All eleven expected fields present. Fields
deliberately *added* to guarantee standalone replayability: `prompt_version`,
`system_prompt`, `model_params`, and full chunk `text`.

**Reconstruction limits, stated rather than hidden:** provider server-side
timestamps and real network round-trip latencies (`timings_ms`) cannot be
reconstructed from a static trace.

This is the substantive point of the exercise: **the trace schema was designed
by attempting a replay and recording what was missing.** A schema designed
without that test always turns out to be missing something.

### 19.4 The demo-set comparison

The most uncomfortable finding, and the reason `is_demo` exists in the
generator.

| Sample | `v2_signature_returned_for_v3_query` frequency |
|---|---:|
| Random sample of real traffic (20 traces) | **35.0%** (7 / 20) |
| Curated weekly demo set (10 traces) | **20.0%** (2 / 10) |

From `notes.md`:

> For the past month, the team has been assuring management that SDK
> documentation retrieval was working smoothly at 80%+ accuracy because our
> weekly DX demo set heavily featured basic conceptual queries and hand-curated
> questions that never queried version-specific method signatures. By testing
> only clean, curated happy-path questions during reviews, we masked the fact
> that 35% of real developer queries receive broken, outdated v2 code
> signatures.

**The generalisable lesson:** a curated demo set drifts towards questions the
system already answers well, because those are the ones that demo well. The
only defence is a seeded random sample of real traffic. This is precisely why
the sampling seed is published.

### 19.5 The dated prediction

From `prediction.md`:

- **Date:** 2026-09-01
- **Target:** `v2_signature_returned_for_v3_query` (35.0% frequency)
- **Change:** metadata filtering on `sdk_version` in `vector_store.query()` and
  `bm25.search()`, combined with version extraction in the query transformer
- **Expected delta:** reduce that mode from **35.0% (7/20)** to **under 5.0%
  (<1/20)** on random developer traces, and raise hit-rate@3 on versioned SDK
  queries from 65% to >90%
- **Pinned commit:** `9276f3b8596b161586b4b4e89ff98215b7216a89`

The prediction is falsifiable on all three axes: a specific mode, a specific
numeric threshold, and a specific code change. It has **not yet been
implemented or tested** — `vector_store.query()` currently accepts no `where`
filter, and no `sdk_version` metadata is written at ingest. That is the next
piece of work (§25).

### 19.6 Public benchmarks — why they would have missed all of this

From `notes.md`:

> Public benchmarks like MMLU or HumanEval measure static multiple-choice
> domain knowledge or standard single-file code completion against fixed
> Python/JS standard libraries. They do not contain proprietary SDK version
> transitions (such as v2 to v3 parameter breaking changes), project-specific
> authorization header conventions, or doc-specific tokenization edge cases
> like wildcard permission characters. Consequently, an app can score 85%+ on
> public benchmarks while failing over a third of real-world developer queries.

Which is the same argument the golden set makes at the retrieval layer: the
only measurement that predicts your system's behaviour is one built on your
corpus and your users' questions.

---

## 20. HTTP API Reference

Base URL: `http://localhost:8000`. All application routes are mounted under
`/api` via `app.include_router(router, prefix="/api")`.

CORS allows exactly one origin — the Vite dev server:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### `GET /health`

```json
{ "status": "ok" }
```

Not under `/api`. Liveness only — it does not check ChromaDB or the BM25 index.

### `POST /api/documents`

Upload and ingest a PDF. `multipart/form-data`, field name `file`.

**Response `200`**

```json
{ "doc_id": "b3f816c32b0b46c1bf5520e689f981d8",
  "filename": "Advita DOCs.pdf",
  "chunks": 14 }
```

| Status | Cause |
|---|---|
| `400` | Filename does not end in `.pdf` |
| `422` | No text extracted even with OCR — the file is deleted from disk |
| `500` | OCR misconfiguration (missing Poppler/Tesseract), unreadable PDF |

### `GET /api/documents`

```json
[ { "doc_id": "b3f816c3...", "filename": "Advita DOCs.pdf", "chunks": 14 },
  { "doc_id": "def7d74f...", "filename": "Cim Authentication.pdf", "chunks": 11 } ]
```

Derived by scanning chunk metadata, so `chunks` is always the true current
count.

### `GET /api/chunks`

Optional query parameter `doc_id`.

```json
[ { "id": "b3f816c32b0b46c1bf5520e689f981d8_0",
    "doc_id": "b3f816c32b0b46c1bf5520e689f981d8",
    "filename": "Advita DOCs.pdf",
    "page": 1,
    "chunk_index": 0,
    "text": "Advita (Cimplicity) — Full Business Workflow...",
    "word_count": 842,
    "char_count": 5127 } ]
```

Sorted by `(filename, chunk_index, page)`. Returns **full chunk text** — this
is the introspection endpoint, so truncation would defeat its purpose.

### `DELETE /api/documents/{doc_id}`

```json
{ "status": "deleted", "doc_id": "b3f816c3..." }
```

Deletes every chunk with that `doc_id` and rebuilds the BM25 index. The
original PDF in `data/uploads/` is **not** removed — see §24.

### `POST /api/query`

The main endpoint.

**Request**

```json
{
  "question": "What does BILL-RESTOCK mean?",
  "top_k": 3,
  "hybrid": true,
  "rerank": false,
  "rewrite": false,
  "mmr": false,
  "hyde": false,
  "retrieval_only": false
}
```

Only `question` is required. `top_k`, `hybrid`, `rerank`, `rewrite` and `mmr`
are `bool | int | None` — **`null` means inherit from `.env`**, not "off".
`hyde` and `retrieval_only` are plain booleans defaulting to `false`.

**Response `200`**

```json
{
  "answer": "BILL-RESTOCK is an order type that both bills the customer and restocks inventory [Advita DOCs.pdf p.2].",
  "sources": [
    { "id": "b3f816c3..._1", "filename": "Advita DOCs.pdf", "page": 2,
      "score": 0.0328, "rank": 1,
      "text": "full chunk text...",
      "retrievers": { "dense": { "rank": 4, "score": 0.71, "rrf_contribution": 0.015625 },
                      "bm25":  { "rank": 1, "score": 8.42, "rrf_contribution": 0.016393 } },
      "rrf_score": 0.0328,
      "rerank_score": null,
      "pre_rerank_score": null }
  ],
  "trace": { "...": "see §14" }
}
```

| Status | Cause |
|---|---|
| `400` | Missing API key, or the provider returned no `choices` |
| `502` | Provider returned an HTTP error |

Two special-cased successful responses: no matches (a fixed explanatory
message, `sources: []`) and `retrieval_only` (answer is the literal string
`"(retrieval_only=true — generation skipped)"`, sources populated).

### `POST /api/triage`

**Request**

```json
{
  "question": "What happens if disableSecurityCheck is true?",
  "expected": [{ "filename": "Cim Authentication.pdf", "page": 6 }],
  "top_k": 3,
  "hybrid": true,
  "generate": true
}
```

**Response `200`**

```json
{
  "question": "...",
  "verdict": "retrieval_failure",
  "reasoning": "RETRIEVAL FAILURE. None of the expected pages (Cim Authentication.pdf p.6) appeared in the top 3. Retrieved instead: Cim Authentication.pdf p.5, Cim Authentication.pdf p.7, Cim Authentication.pdf p.10.",
  "retrieved_correct_chunk": false,
  "first_hit_rank": 4,
  "hit_at_k": false,
  "recall_at_k": 0.0,
  "reciprocal_rank": 0.25,
  "sources": [ ... ],
  "answer": "...",
  "trace": { ... }
}
```

`verdict` is one of `retrieval_failure`, `partial_retrieval`,
`generation_candidate`.

### `GET /api/golden-set`

Returns `eval/golden_set.json` verbatim, including `_readme`. `404` if the
file is absent.

### `POST /api/evaluate`

**Request**

```json
{ "config": "hybrid", "top_k": 3 }
```

**Response `200`** — the full run object: `config_name`, `config`,
`description`, `top_k`, `overall`, `by_category`, and a `questions` array with
per-question chunks, ranks and traces.

`400` if the config name is unknown; the error lists valid names.

This runs 25 retrievals synchronously. With `rerank` or `rewrite` enabled it
can take tens of seconds.

### `GET /api/configs`

```json
[ { "name": "baseline",
    "description": "Dense vector search only — the Week 3 app, unchanged",
    "flags": { "hybrid": false, "rerank": false, "rewrite": false, "mmr": false } } ]
```

`_`-prefixed keys are stripped from `flags`.

### `GET /api/retrieval-settings`

```json
{
  "top_k": 4,
  "hybrid_enabled": true,
  "rerank_enabled": false,
  "rewrite_enabled": false,
  "mmr_enabled": false,
  "candidate_k": 20,
  "rrf_k": 60,
  "mmr_lambda": 0.7,
  "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "embedding_model": "all-MiniLM-L6-v2",
  "bm25_index_size": 25
}
```

`bm25_index_size` is the live in-memory index size, obtained by calling
`ensure_bm25_index()` without `force` — a build-if-needed read.

### Interactive docs

FastAPI serves Swagger UI at `/docs` and ReDoc at `/redoc`, generated from the
Pydantic schemas — no annotation maintenance required.

---

## 21. Frontend Architecture

### 21.1 Shell — `src/App.jsx`

120 lines. Four tabs, three pieces of state, no router and no state library:

```jsx
const TABS = [
  ['chat',    'Chat'],
  ['inspect', 'Retrieval Inspector'],
  ['eval',    'Measurement'],
  ['chunks',  'Document Chunks'],
]

export default function App() {
  const [tab, setTab] = useState('chunks')
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [docRefreshKey, setDocRefreshKey] = useState(0)
  ...
}
```

**Cross-tab navigation** is the one piece of coordination: clicking a
document's chunk count in the sidebar sets `selectedDocId` and switches to the
Chunks tab.

```jsx
function handleViewChunks(docId) {
  setSelectedDocId(docId)
  setTab('chunks')
}
```

**`docRefreshKey`** is a monotonically-increasing counter passed to
`ChunksPanel` as `refreshKey`. When `DocumentPanel` reports a change, the
counter increments, `ChunksPanel`'s effect re-fires, and chunks reload. A
minimal, explicit invalidation signal instead of a global store.

Three tabs (`chat`, `inspect`, `chunks`) render `DocumentPanel` in a
`280px + 1fr` grid; `eval` is full width because it has nothing document-scoped
to show.

### 21.2 API client — `src/api.js`

Ten thin `fetch` wrappers with a uniform error convention:

```js
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

export async function askQuestion(question, options = {}) {
  const res = await fetch(`${BASE_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...options }),
  })
  if (!res.ok) throw new Error((await res.json()).detail || 'Query failed')
  return res.json()
}
```

Every function throws on `!res.ok`, unwrapping FastAPI's `detail` field so the
backend's error text reaches the user verbatim. Components catch and render it.

| Function | Endpoint |
|---|---|
| `uploadDocument(file)` | `POST /documents` |
| `listDocuments()` | `GET /documents` |
| `deleteDocument(docId)` | `DELETE /documents/{id}` |
| `listChunks(docId?)` | `GET /chunks` |
| `askQuestion(q, opts)` | `POST /query` |
| `triage(payload)` | `POST /triage` |
| `getGoldenSet()` | `GET /golden-set` |
| `runEvaluation(cfg, k)` | `POST /evaluate` |
| `listConfigs()` | `GET /configs` |
| `getRetrievalSettings()` | `GET /retrieval-settings` |

`options` in `askQuestion` is spread directly into the body, so the strategy
toggles map one-to-one onto `QueryRequest` fields with no translation layer.

### 21.3 DocumentPanel — 211 lines

Sidebar: upload zone plus document list.

**Drag-and-drop** with a four-event handler and an `dragActive` state that
drives the border/background treatment:

```jsx
const handleDrag = (e) => {
  e.preventDefault(); e.stopPropagation()
  if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
  else if (e.type === 'dragleave') setDragActive(false)
}
```

The whole zone is also click-to-browse, driving a hidden
`<input type="file" accept="application/pdf">` through a ref. The file input
value is cleared in `finally` so re-selecting the same file re-fires `onChange`.

An absolutely-positioned "Indexing…" overlay with a spinner covers the zone
during upload — necessary because ingestion is synchronous and can take
seconds.

Each document row shows filename, a clickable `N chunks` pill, an "Indexed"
status dot, and a delete button that appears on hover
(`opacity-0 group-hover:opacity-100`).

### 21.4 ChatPanel — 147 lines

The simplest surface: a message list plus an input.

Messages carry one of three roles — `user`, `assistant`, `error` — each with
its own bubble treatment. Assistant messages render through `react-markdown`
with `remark-gfm`, and tables get a custom renderer so wide tables scroll
inside their own container rather than breaking the layout:

```jsx
<Markdown
  remarkPlugins={[remarkGfm]}
  components={{
    table: ({ node, ...props }) => (
      <div className="overflow-x-auto my-3 rounded-lg border border-slate-700/50">
        <table className="w-full text-xs border-collapse" {...props} />
      </div>
    ),
  }}
>
  {m.text}
</Markdown>
```

Sources render in a collapsed `<details>` showing `filename · p.N · (score)`.

`askQuestion(q)` is called with **no options**, so the Chat tab always uses the
server's `.env` defaults. That is deliberate: Chat is the product, the
Inspector is the lab.

### 21.5 InspectorPanel — 730 lines, the centrepiece

The retrieval debugger. Five regions:

**1. Test Your Retrieval.** A free-text query box, plus a golden-question
dropdown. Selecting a golden question fills the query and reveals its expected
pages:

```jsx
{goldenQ && (
  <div className="mt-3 p-3 rounded-lg bg-blue-500/10 ...">
    <div className="text-blue-200 font-medium mb-1">Expected documents:</div>
    <div className="text-blue-200/70">
      {goldenQ.expected.map((e) => `${e.filename} (p. ${e.page})`).join(', ')}
    </div>
  </div>
)}
```

Two actions: **Run Retrieval** (`POST /query`) and, when a golden question is
selected, **Diagnose** (`POST /triage`).

**2. Retrieval Pipeline.** Five toggle pills — Hybrid Search, Rerank, Query
Rewrite, HyDE, MMR — plus numeric inputs for Top K / Candidate K / RRF K and a
"Retrieval only (skip LLM generation)" checkbox. Below them, a Pipeline Summary
renders the active stages as a `→` chain with a four-metric strip: candidate
pool, final results, RRF K, and live BM25 index size from
`GET /retrieval-settings`.

**3. Triage verdict.** A colour-coded card — red for `retrieval_failure`, amber
for `partial_retrieval`, emerald for success — carrying the reasoning sentence
and a four-cell metric grid (first hit rank, hit@k, recall@k, reciprocal rank).

**4. Results grid.** Two columns.

*Retrieved Documents* — one card per chunk with rank badge, filename, page,
score, and:

- an **Expected** green badge when `(filename, page)` matches the golden
  question's expected set — instant visual confirmation of a hit
- **retriever provenance badges** rendered straight from the `retrievers` dict:

  ```jsx
  {Object.entries(s.retrievers).map(([name, info]) => (
    <span key={name} className="badge badge-slate text-xs">
      {name} #{info.rank}
    </span>
  ))}
  ```

  This renders as `dense #4` `bm25 #1` — the single most useful debugging
  affordance in the app.
- `rerank_score` shown alongside `score` when reranking ran
- a 150-character preview with Show/Hide full text

*Generated Answer* — markdown-rendered, with a metadata strip (sources used,
latency from `trace.timings_ms.total`) and a Copy Answer button.

**5. Retrieval Diagnostics.** A collapsible panel rendering the trace: the
query rewrite before/after when they differ, each pipeline stage with its
stage-specific fields (fused count and agreement for RRF; candidates scored and
`changed_top_k` for rerank), and the full latency breakdown per stage.

**Progressive loading indicator.** A four-step stepper — Rewriting →
Retrieving → Reranking → Generating — advancing on a 450ms interval, with
Rewriting struck through when the toggle is off:

```jsx
function runLoadingSteps() {
  setLoadingStep(0)
  const stepCount = strategies.rewrite ? PIPELINE_STEPS.length : PIPELINE_STEPS.length - 1
  const interval = setInterval(() => {
    setLoadingStep((s) => (s < stepCount - 1 ? s + 1 : s))
  }, 450)
  return () => clearInterval(interval)
}
```

This is a *cosmetic* progress indicator — it advances on a timer, not on real
stage completion, since the backend returns one response at the end rather than
streaming stage events.

### 21.6 EvalPanel — 291 lines

Runs the golden set under each configuration and diffs any two runs.

Configurations load from `GET /configs`. Each row has a Run button; completed
runs get an inline green badge showing `hit@3` and MRR. Every run is kept in a
`runs` object keyed by config name, so a session accumulates a comparison
matrix without re-running anything.

Two dropdowns pick Before and After. Then:

**Metric delta table** — hit@1/3/5, recall@1/3/5, MRR, each with a signed delta
and an up/down class.

**Category table** — per-category hits and percentages for both runs, with the
improving side highlighted.

**Movement columns** — Fixed / Broke / Still broken, computed client-side by
the same set logic the CLI uses:

```jsx
for (const id of Object.keys(bq)) {
  if (!aq[id]) continue
  const was = bq[id]['hit@3']
  const now = aq[id]['hit@3']
  if (!was && now) fixed.push(aq[id])
  else if (was && !now) broke.push(aq[id])
  else if (!was && !now) still.push(aq[id])
}
```

**"Still broken" is given equal visual weight to "Fixed."** That is a design
decision, not an accident — it is the column that keeps the analysis honest.

### 21.7 ChunksPanel — 458 lines

The Document Chunks Explorer, added last and motivated by the q01 finding.

**Four stat cards** — total chunks, document count, average words per chunk,
filtered matches — computed with `useMemo` over the loaded chunk array.

**Three-way filtering**, also memoised:

```jsx
const filteredChunks = useMemo(() => {
  const q = searchQuery.trim().toLowerCase()
  return chunks.filter((chunk) => {
    if (selectedDocId !== 'all' && chunk.doc_id !== selectedDocId) return false
    if (selectedPage !== 'all' && String(chunk.page) !== String(selectedPage)) return false
    if (q) {
      const inText = (chunk.text || '').toLowerCase().includes(q)
      const inDoc  = (chunk.filename || '').toLowerCase().includes(q)
      const inId   = (chunk.id || '').toLowerCase().includes(q)
      if (!inText && !inDoc && !inId) return false
    }
    return true
  })
}, [chunks, selectedDocId, selectedPage, searchQuery])
```

Search spans chunk text, filename **and chunk id** — so a chunk id copied out
of a trace pastes straight into the search box and lands on the chunk.

**Page filter options are derived** from the current document selection, so the
dropdown never offers a page that does not exist in the active filter.

**Match highlighting** splits on a regex built from the escaped query and wraps
matches in `<mark>`:

```jsx
const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
```

The escape is necessary — without it, searching for `*` or `(` throws.

Plus expand/collapse per chunk, an Expand All toggle, and per-chunk
copy-to-clipboard with a 1.8s confirmation.

**Why this panel exists.** The Week 4 conclusion was that q01 fails because a
table is split across a page boundary. Verifying that claim previously meant
querying ChromaDB by hand. Now it is: filter to the document, filter to page 2,
read the chunk.

### 21.8 Icons and styling

`icons.jsx` exports 21 inline SVG components — `IconDatabase`, `IconSettings`,
`IconUpload`, `IconFile`, `IconTrash`, `IconInbox`, `IconPlay`, `IconSearch`,
`IconLoader`, `IconChevron`, `IconCheck`, `IconCircle`, `IconCopy`, `IconAlert`,
`IconCheckCircle`, `IconX`, `IconSparkle`, `IconMessage`, `IconLayers`,
`IconFilter`, `IconEye`. Each spreads props, so size and className are
caller-controlled. Zero dependency, zero icon-font FOUC, tree-shakeable by
construction.

`tailwind.config.js` defines the palette and elevation tokens:

```js
colors: {
  'dark-bg':      '#08111F',
  'dark-card':    '#0F1B2E',
  'dark-surface': '#1a2540',
  'dark-border':  '#2a3f5f',
  'status-success': '#10b981',
  'status-warning': '#f59e0b',
  'status-error':   '#ef4444',
},
boxShadow: {
  'card':       '0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24)',
  'card-hover': '0 3px 6px rgba(0,0,0,.16), 0 3px 6px rgba(0,0,0,.23)',
  'glow':       '0 0 0 1px rgba(148,163,184,.08), 0 20px 45px rgba(15,23,42,.45)',
  'accent':     '0 0 20px rgba(59,130,246,.2)',
}
```

`index.css` (489 lines) layers a semantic component vocabulary on top —
`.card-modern`, `.card-header`, `.card-title`, `.nav-tab`, `.toggle-pill`,
`.form-input`, `.settings-input`, `.btn-primary`, `.btn-secondary`, `.btn-icon`,
`.badge-{blue,green,amber,slate}`, `.result-card`, `.result-rank`,
`.result-score`, `.status-dot`, `.metrics`, `.movement`, `.custom-scrollbar`,
`.markdown-body`. Components compose these named classes rather than repeating
long utility strings, which is what keeps 2,650 lines of JSX readable.

`lib/utils.js` provides the standard merge helper:

```js
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
```

`clsx` handles conditionals; `twMerge` resolves Tailwind conflicts so a later
`border-blue-500/60` correctly overrides an earlier `border-slate-700/40`.

---

## 22. End-to-End Walkthrough

One question, all the way through, with hybrid enabled and `top_k = 3`.

**Question:** *"What happens if disableSecurityCheck is true?"*

### Step 1 — the browser

`InspectorPanel.handleAsk` fires:

```js
const res = await askQuestion("What happens if disableSecurityCheck is true?", {
  hybrid: true, rerank: false, rewrite: false, mmr: false, hyde: false,
  top_k: 3, retrieval_only: false,
})
```

`POST http://localhost:8000/api/query` with that JSON body.

### Step 2 — route entry

`routes/query.py` logs the request and delegates:

```
[QUESTION FLOW] request.received {"question": "What happens if disableSecurityCheck is true?", "top_k": 3, "hybrid": true, ...}
```

### Step 3 — flag resolution

`retrieve()` resolves each flag. `hybrid=True` was supplied, so it wins.
`rerank=False` was supplied explicitly. The trace skeleton is built with the
resolved config.

### Step 4 — Stage 1, query transform

`do_rewrite` and `hyde` are both false. `search_query = question`, no stage
recorded, no LLM call, no latency.

### Step 5 — Stage 2a, dense search

`needs_candidates` is true (hybrid), so `fetch_n = max(20, 3) = 20`.

`vector_store.query(search_query, top_k=20)` embeds the question with
all-MiniLM-L6-v2 and runs an HNSW cosine search. Distances become similarities
via `1 - dist`.

```
dense results (top 5):
  #1  CimAuth p.5   score 0.7412
  #2  CimAuth p.7   score 0.7108
  #3  CimAuth p.10  score 0.6934
  #4  CimAuth p.6   score 0.6871   <- the correct page, ranked 4th
  #5  Advita  p.3   score 0.6522
```

Trace stage: `{"stage": "dense_search", "returned": 20, "top": [...]}`.
Timing: ~41ms.

### Step 6 — Stage 2b, BM25 search

`ensure_bm25_index()` finds the index already built (25 chunks). BM25 searches
the **original** question. Tokenisation gives:

```
["what", "happens", "if", "disablesecuritycheck", "is", "true"]
```

`disablesecuritycheck` appears in exactly 1 of 25 chunks, so its IDF is large
and that chunk's score dominates:

```
bm25 results (top 5):
  #1  CimAuth p.6   score 8.4213   <- the correct page, ranked 1st
  #2  CimAuth p.5   score 2.1104
  #3  CimAuth p.9   score 1.8871
  #4  Advita  p.7   score 1.2033
  #5  CimAuth p.7   score 0.9812
```

Trace stage records `query_terms`, so a tokenisation problem would be visible
here. Timing: ~2ms.

### Step 7 — Stage 2c, RRF fusion

```
p.6:  dense #4 -> 1/64 = 0.015625
      bm25  #1 -> 1/61 = 0.016393
      rrf_score = 0.032018        <- highest

p.5:  dense #1 -> 1/61 = 0.016393
      bm25  #2 -> 1/62 = 0.016129
      rrf_score = 0.032522        <- also high
```

Both chunks got two votes. Fusion output places them at the top; **p.6 is now
inside the top 3, where dense search alone had it at rank 4.**

Trace stage:

```json
{ "stage": "rrf_fusion", "rrf_k": 60, "fused_count": 24,
  "bm25_only_in_top_k": ["def7d74f..._9"],
  "dense_only_in_top_k": ["def7d74f..._13"],
  "agreed_in_top_k": ["def7d74f..._5", "def7d74f..._6"] }
```

Timing: ~0.4ms.

### Step 8 — Stages 3 and 4

`do_rerank` and `do_mmr` are false. Both skipped, no stages recorded.

### Step 9 — finalise

Slice to `top_k = 3`, assign 1-based ranks, record `final_chunk_ids` and
`retrieval_order_before_rerank`, sum timings to ~43.5ms total.

### Step 10 — generation

`llm_client.generate_answer()` builds the context block:

```
[Cim Authentication.pdf p.6]
...disableSecurityCheck: when set to true, route-level permission validation is
bypassed entirely for the request...

---

[Cim Authentication.pdf p.5]
...

---

[Cim Authentication.pdf p.7]
...
```

POSTs to the configured provider with the system prompt plus
`Context:\n{context}\n\nQuestion: {question}`. Response parsed, `choices[0]`
checked, answer extracted.

### Step 11 — trace persistence

`log_interaction_trace()` writes one JSON line to `data/traces.jsonl` with the
full chunk text, the system prompt, the model, the model params, the config,
the stages and the timings. Its `trace_id` is back-filled into the response
trace.

### Step 12 — the response

```json
{
  "answer": "When disableSecurityCheck is true, route-level permission validation is bypassed entirely for that request [Cim Authentication.pdf p.6].",
  "sources": [
    { "rank": 1, "filename": "Cim Authentication.pdf", "page": 6,
      "score": 0.032018,
      "retrievers": { "dense": {"rank": 4, ...}, "bm25": {"rank": 1, ...} },
      "text": "..." },
    { "rank": 2, ... },
    { "rank": 3, ... }
  ],
  "trace": { ... }
}
```

### Step 13 — rendering

The Inspector renders three result cards. The first shows
`dense #4` and `bm25 #1` badges — **and that is the whole story of why hybrid
search fixed this question, visible at a glance.** The Diagnostics panel below
shows the fusion stage and the 43.5ms latency breakdown.

If the golden question was selected, the p.6 card also carries a green
**Expected** badge, and clicking Diagnose returns
`verdict: "generation_candidate"` with `first_hit_rank: 1`.

---

## 23. Operations — Setup, Run, Debug

### 23.1 Prerequisites

- Python 3.11+ (the venv in this repo is 3.11)
- Node.js 18+
- **Tesseract OCR** — only for scanned PDFs
- **Poppler** — only for scanned PDFs

On Windows both are available via winget:

```powershell
winget install UB-Mannheim.TesseractOCR
winget install oschwartz10612.Poppler
```

Both modify `PATH`, and **the change does not apply to already-open shells** —
restart the terminal, or set the explicit paths in `.env`.

### 23.2 Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env: add your API key, fix the OCR paths for THIS machine
python -m uvicorn app.main:app --reload --port 8000
```

Successful startup prints:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
[startup] BM25 keyword index built over 25 chunks
INFO:     Application startup complete.
```

The `Failed to send telemetry event ...: capture() takes 1 positional argument
but 3 were given` lines are a known ChromaDB 0.5.20 telemetry incompatibility.
They are harmless and do not affect indexing or retrieval.

### 23.3 Frontend

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open `http://localhost:5173`.

### 23.4 Configuring OCR paths correctly

Verify the binaries first:

```powershell
where.exe tesseract
where.exe pdfinfo
```

If both resolve, leave both settings **blank** in `.env` and the libraries will
use `PATH`.

If they do not resolve, set explicit paths — and make sure they exist on *this*
machine:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
POPPLER_PATH=C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin
```

> **Critical.** `POPPLER_PATH` is passed to `pdf2image` as `poppler_path`,
> which **overrides `PATH` entirely**. A stale absolute path copied from a
> teammate's `.env` produces `PDFInfoNotInstalledError: Unable to get page
> count. Is poppler installed and in PATH?` even when Poppler is installed
> correctly and on `PATH`. These paths are per-machine and must never be
> shared between developers.

Verify the whole OCR chain without the HTTP layer:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from app.services.pdf_loader import _ocr_page; print(len(_ocr_page('data/uploads/<file>.pdf', 1)))"
```

A non-zero character count means Poppler and Tesseract are both wired up.

### 23.5 Running the evaluation harness

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

.venv\Scripts\python -m eval.run_eval --list-configs
.venv\Scripts\python -m eval.run_eval --config baseline --save
.venv\Scripts\python -m eval.run_eval --config hybrid --save
.venv\Scripts\python -m eval.run_eval --compare baseline hybrid
.venv\Scripts\python -m eval.run_eval --sweep --save
.venv\Scripts\python -m eval.run_eval --config hybrid --question q15 --verbose
```

The harness needs the vector store populated; it exits with a clear message if
the index is empty.

### 23.6 Trace tooling

```powershell
.venv\Scripts\python eval\generate_traces.py                    # regenerate 100 traces
.venv\Scripts\python eval\replay_trace.py --sample --seed 20260901
.venv\Scripts\python eval\replay_trace.py --replay tr_042
```

> `generate_traces.py` **overwrites** `data/traces.jsonl` with exactly 100
> generated records, discarding any live-logged traces appended since the last
> run. The current file has 104 records — 100 generated plus 4 live — and
> regenerating would lose those 4.

### 23.7 VS Code debugging — `.vscode/launch.json`

```json
{
  "name": "Python Debugger: FastAPI",
  "type": "debugpy",
  "request": "launch",
  "module": "uvicorn",
  "args": ["app.main:app", "--reload", "--port", "8000"],
  "cwd": "${workspaceFolder}/backend",
  "python": "${workspaceFolder}/backend/.venv/Scripts/python.exe",
  "subProcess": true,
  "console": "integratedTerminal",
  "jinja": true
}
```

Two settings are load-bearing and both are commented in the file:

- **`cwd` must be `backend/`** — uvicorn resolves `app.main:app` relative to
  the working directory, and the relative paths in `.env`
  (`./data/chroma`, `./data/uploads`) resolve from there too.
- **`subProcess: true`** — `--reload` spawns a child process to run the app.
  Without this, breakpoints bind only in the parent watcher and never hit.

### 23.8 Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `PDFInfoNotInstalledError` | `POPPLER_PATH` points at a non-existent directory | Correct or blank it; restart the server |
| `TesseractNotFoundError` | `TESSERACT_CMD` wrong or Tesseract absent | Install, or correct the path |
| `422` on upload | PDF has no extractable text and OCR failed | Check OCR setup; confirm the PDF is not encrypted |
| `400` "API key is not set" | Missing key for the *selected* provider | Set `OPENROUTER_API_KEY` or `GROQ_API_KEY` to match `OPENROUTER_ENABLED` |
| `502` from `/api/query` | Provider returned an HTTP error | Check credit, model id, rate limits |
| `400` "returned no choices" | Provider returned 200 with an error body | Usually model unavailable or no credit |
| `[startup] BM25 index built over 0 chunks` | Empty vector store | Upload a PDF |
| Eval exits "No chunks in the vector store" | Same | Upload before evaluating |
| First rerank run hangs ~30s | Downloading the ~90MB cross-encoder | One-time; needs network |
| CORS error in browser | Frontend not on `:5173` | Add the origin in `main.py` |
| Settings change has no effect | `Settings()` is built at import; `--reload` watches `.py` only | Restart the server after editing `.env` |

That last row is worth internalising: **`.env` changes require a server
restart**, because `settings = Settings()` runs once at import and uvicorn's
`--reload` watcher only fires on Python file changes.

---

## 24. Known Issues and Limitations

Stated plainly. Everything here is a real, verified gap in the current code.

### 24.1 Configuration drift between code and docs

`config.py` sets `hybrid_enabled: bool = True`, but both `.env.example`
(`HYBRID_ENABLED=false`) and README's "All four strategy toggles default to
**off**" say otherwise. The code default is correct — hybrid was deliberately
shipped per §18.7 — but the documentation was not updated to match. A reader
following the README will believe the default app is the dense-only baseline
when it is not.

### 24.2 Inspector's Candidate K and RRF K inputs are inert

`InspectorPanel` renders numeric inputs for Candidate K and RRF K and stores
them in state, but `handleAsk` sends only `{...strategies, top_k, retrieval_only}`:

```jsx
const res = await askQuestion(q, { ...strategies, top_k: topK, retrieval_only: retrievalOnly })
```

`QueryRequest` has no `candidate_k` or `rrf_k` fields either, so even if they
were sent they would be ignored. Both values are read from `settings` inside
`retrieve()`. **Changing them in the UI changes only the Pipeline Summary
display, not retrieval behaviour.** Fixing this means adding both fields to
`QueryRequest` and threading them through `retrieve()`.

### 24.3 Hardcoded model label in the Inspector

The Generated Answer metadata strip renders a literal string:

```jsx
<div className="flex justify-between">
  <span>Model</span>
  <span className="font-mono text-slate-300">GPT</span>
</div>
```

It says "GPT" regardless of the configured provider or model. The real model id
is available from `GET /api/retrieval-settings`-adjacent data and in every
trace record; it just is not wired up.

### 24.4 Deleted documents leave their PDFs on disk

`DELETE /api/documents/{doc_id}` removes chunks from ChromaDB and rebuilds the
BM25 index, but the original file in `data/uploads/` is never removed. Over
time the upload directory accumulates orphans. The current directory already
shows five copies of `Advita DOCs.pdf` under different UUID prefixes.

### 24.5 Ingestion is synchronous and blocking

A large scanned PDF runs OCR at ~1s/page inside the request handler. A 200-page
scan is a 200-second HTTP request — past most proxy timeouts. Needs a
background task with a job-status endpoint.

### 24.6 BM25 rebuilds fully on every change

Uploading ten documents triggers ten full index rebuilds. Fine at 25 chunks,
quadratic-feeling at 100k. Needs either incremental updates or debounced
rebuilds.

### 24.7 BM25 search is a linear scan

`search()` scores every chunk in the corpus for every query. At 25 chunks this
is microseconds; at 100k it needs an inverted index so only chunks containing a
query term are touched.

### 24.8 The tokenizer drops symbols

`[A-Za-z0-9_-]+` excludes `*`, `/`, `.`, `:`, `#`, `@`. Questions *about* those
characters cannot match on them. Measured as a real failure (§18.6) and
independently rediscovered as taxonomy mode
`wildcard_and_special_char_token_dropped` (§19.2).

### 24.9 Context assembly is duplicated

`llm_client.build_context_block()` and the reconstruction inside
`replay_trace.replay_trace()` implement the same format independently. If one
changes, replay silently stops being faithful. They should share one function.

### 24.10 `generate_traces.py` overwrites live traces

It opens `traces.jsonl` with mode `"w"`. Any live-logged traces appended since
the last generation are destroyed. The current file holds 4 such records.

### 24.11 Traces grow without bound

`trace_logger` appends forever with no rotation, no size cap and no retention
policy. Each record carries **full chunk text** for every retrieved chunk, so a
busy instance grows fast.

### 24.12 Trace records may contain sensitive document text

By design, each record stores the complete text of every retrieved chunk. For a
corpus containing confidential material, `traces.jsonl` is as sensitive as the
corpus itself — and it is currently **tracked in git**. Anything beyond local
experimentation needs this reconsidered.

### 24.13 No automated tests

There is no test suite. The evaluation harness measures retrieval *quality* but
asserts nothing about correctness: nothing verifies that `chunk_text` respects
its overlap, that `_page_key` normalises as intended, that RRF arithmetic is
right, or that `_clean_rewrite` rejects what it should. These are all pure
functions and would be straightforward to cover.

### 24.14 No authentication

Every endpoint is unauthenticated. Anyone who can reach the port can upload,
query, delete, and read every chunk of every document.

### 24.15 Single-collection, single-tenant

One hardcoded ChromaDB collection named `documents`. No per-user or per-project
separation. Every uploaded document is searchable by every query.

### 24.16 No streaming responses

`/api/query` returns one JSON body after generation completes. Users watch a
spinner for the full duration. The Inspector's four-step progress indicator is
a timer, not real progress.

### 24.17 Evaluation is synchronous over HTTP

`POST /api/evaluate` runs 25 retrievals in the request handler. With `rerank`
or `rewrite` enabled this takes tens of seconds and can hit client timeouts.

### 24.18 `list_documents()` scans all metadata

It fetches every chunk's metadata to count documents. O(chunks) for what should
be a cheap aggregate.

### 24.19 The `everything` config has no saved result

`eval/results/` contains seven files; `everything` is missing. A `--sweep` run
would produce it, but the ceiling-check number is currently absent from the
saved record.

### 24.20 The Week 5 prediction is untested

`prediction.md` proposes `sdk_version` metadata filtering. No such metadata is
written at ingest, and `vector_store.query()` accepts no `where` filter. The
prediction stands unfalsified because the experiment has not been run.

---

## 25. Roadmap

Ordered by the ratio of measured evidence to implementation cost.

### Tier 1 — close the loop on what is already measured

**1. Fix the chunking failure behind q01.** The single measured failure no
retrieval strategy fixed. The definition of `BILL-RESTOCK` sits in a table
split across pages 2–3. Options: structure-aware chunking that keeps table rows
intact, or a small overlap *across* page boundaries. This has a ready-made
test — q01 flips from miss to hit, or it does not.

**2. Run the Week 5 prediction.** Add `sdk_version` to chunk metadata at
ingest, add a `where` filter to `vector_store.query()`, extract the version
from the question in the query transformer. Then re-sample 20 traces with the
same seed and measure whether `v2_signature_returned_for_v3_query` drops below
5%. The prediction is dated and pinned to a commit; running it is the whole
point.

**3. Widen the tokenizer.** Add `*` and other operator symbols, or a
symbol-alias table (`*` → `wildcard`, `-L` → `suffix_l`). Directly targets the
20%-frequency taxonomy mode and the measured q20/q04 failures. Guard against
regression by re-running the sweep.

**4. Reconcile the documentation drift.** Update `.env.example` and README to
reflect `HYBRID_ENABLED=true` as shipped (§24.1).

### Tier 2 — correctness and hygiene

**5. Wire up Candidate K and RRF K** end to end (§24.2), so the Inspector's
controls do what they appear to do.

**6. Show the real model name** in the Inspector (§24.3).

**7. Delete the PDF when its document is deleted** (§24.4).

**8. Extract shared context assembly** so `llm_client` and `replay_trace` cannot
diverge (§24.9).

**9. Make `generate_traces.py` append-or-confirm** instead of silently
overwriting (§24.10).

**10. Add a unit test suite** over the pure functions: `chunk_text`,
`tokenize`, `_idf`, `reciprocal_rank_fusion`, `_page_key`, every metric,
`_clean_rewrite`. Fast, deterministic, and they cover the logic most likely to
break silently.

### Tier 3 — scale

**11. Background ingestion** with a job-status endpoint (§24.5).

**12. Streaming generation** via SSE, with real per-stage progress events
replacing the cosmetic stepper (§24.16).

**13. Inverted index for BM25** and incremental updates (§24.6, §24.7).

**14. Trace rotation and retention** — daily files, size caps, an option to
store chunk ids instead of full text (§24.11, §24.12).

**15. Async evaluation** — start a run, poll for results (§24.17).

### Tier 4 — product

**16. Authentication and multi-tenancy** — per-user collections, scoped
queries (§24.14, §24.15).

**17. Conversation memory.** `ChatPanel` keeps message history in React state
but sends only the current question. Follow-ups like "what about the other
one?" cannot work.

**18. More document formats** — DOCX, HTML, Markdown. `pdf_loader` is the only
format-specific module; the seam already exists.

**19. Semantic chunking** — split on structure (headings, tables, sections)
rather than a fixed word window. This is the general form of fix #1.

**20. Expand the golden set** with multi-fact questions, so MMR can be measured
on the thing it is actually good at (§13.4).

---

## Appendix A — File Index

### Backend application

| File | Lines | Responsibility |
|---|---:|---|
| `app/main.py` | 34 | FastAPI app, CORS, lifespan BM25 build, `/health` |
| `app/core/config.py` | 73 | `Settings` — every configurable value, provider properties |
| `app/core/flow_log.py` | 10 | Structured console tracing |
| `app/api/routes/__init__.py` | 10 | Router aggregation |
| `app/api/routes/documents.py` | 56 | Upload, list, chunks, delete |
| `app/api/routes/query.py` | 133 | The main Q&A endpoint, error translation, tracing |
| `app/api/routes/evaluation.py` | 145 | Triage, evaluate, golden-set, configs, settings |
| `app/api/schemas/documents.py` | 25 | `UploadResponse`, `DocumentInfo`, `ChunkInfo` |
| `app/api/schemas/query.py` | 33 | `QueryRequest`, `SourceChunk`, `QueryResponse` |
| `app/api/schemas/evaluation.py` | 51 | `ExpectedPage`, Triage + Eval models |
| `app/services/pdf_loader.py` | 31 | pypdf extraction + per-page OCR fallback |
| `app/services/chunker.py` | 21 | Sliding word-window chunking |
| `app/services/ingest.py` | 16 | Orchestrates extract → chunk → store |
| `app/services/vector_store.py` | 177 | ChromaDB: add, query, get, embeddings, delete |
| `app/services/bm25.py` | 200 | BM25 index and search, pure Python |
| `app/services/retriever.py` | 464 | The pipeline: RRF, MMR, staging, tracing |
| `app/services/reranker.py` | 114 | Cross-encoder lazy load + rerank |
| `app/services/query_rewriter.py` | 209 | Rewrite, HyDE, reasoning-model cleanup |
| `app/services/llm_client.py` | 94 | Prompt assembly, provider call, error handling |
| `app/services/metrics.py` | 129 | hit-rate@k, recall@k, MRR, aggregation |
| `app/services/trace_logger.py` | 122 | Live interaction persistence to JSONL |

### Evaluation

| File | Lines | Responsibility |
|---|---:|---|
| `eval/run_eval.py` | 413 | CLI harness: run, compare, sweep, report |
| `eval/generate_traces.py` | ~420 | Deterministic 100-trace generator |
| `eval/replay_trace.py` | 128 | Seeded sampler, offline replay, schema audit |
| `eval/golden_set.json` | — | 25 questions, categorised, with `_readme` |
| `eval/golden_set.jsonl` | 12 | Week 4 submission set with `expected_chunk_id` |
| `eval/results/*.json` | 7 files | Saved runs with full per-question traces |

### Frontend

| File | Lines | Responsibility |
|---|---:|---|
| `src/main.jsx` | 10 | React root |
| `src/App.jsx` | 120 | Shell, 4 tabs, cross-tab navigation |
| `src/api.js` | ~90 | 10 fetch wrappers with uniform error handling |
| `src/lib/utils.js` | 6 | `cn()` — clsx + tailwind-merge |
| `src/index.css` | 489 | Design-system component classes |
| `src/components/DocumentPanel.jsx` | 211 | Drag-drop upload, document list, delete |
| `src/components/ChatPanel.jsx` | 147 | Conversational Q&A with markdown |
| `src/components/InspectorPanel.jsx` | 730 | The retrieval debugger |
| `src/components/EvalPanel.jsx` | 291 | Before/after measurement |
| `src/components/ChunksPanel.jsx` | 458 | Chunk explorer with search and filters |
| `src/components/icons.jsx` | 197 | 21 inline SVG icon components |

### Documentation

| File | Lines | Content |
|---|---:|---|
| `README.md` | 94 | Quickstart, API summary, config table |
| `RETRIEVAL_DEBUGGING.md` | 254 | Week 4 narrative: hybrid, rerank, what did not get fixed |
| `IMPLEMENTATION.md` | this | Complete implementation reference |
| `results.md` | 65 | Week 4 practical: failure separation, one change, latency |
| `notes.md` | 102 | Week 5: sampling, replay, open-coding, demo-set comparison |
| `taxonomy.md` | 16 | Week 5: five failure modes with frequency and severity |
| `prediction.md` | 6 | Week 5: dated falsifiable prediction |

---

## Appendix B — Configuration Reference

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_ENABLED` | bool | `true` | `true` = OpenRouter, `false` = Groq |
| `OPENROUTER_API_KEY` | str | `""` | Required when OpenRouter is enabled |
| `GROQ_API_KEY` | str | `""` | Required when Groq is enabled |
| `OPENROUTER_MODEL` | str | `anthropic/claude-3.5-sonnet` | Any OpenRouter model id |
| `GROQ_MODEL` | str | `openai/gpt-oss-20b` | Any Groq model id |
| `EMBEDDING_MODEL` | str | `all-MiniLM-L6-v2` | Local sentence-transformer |
| `CHROMA_DIR` | str | `./data/chroma` | Vector DB persistence path |
| `UPLOAD_DIR` | str | `./data/uploads` | Uploaded PDF storage |
| `TRACES_PATH` | str | `./data/traces.jsonl` | Interaction trace log |
| `TRACE_LOGGING_ENABLED` | bool | `true` | Master switch for trace persistence |
| `CHUNK_SIZE` | int | `1000` | Chunk width in **words** |
| `CHUNK_OVERLAP` | int | `150` | Overlap between chunks in words |
| `TOP_K` | int | `4` | Chunks retrieved per query |
| `TESSERACT_CMD` | str | `""` | Path to `tesseract.exe`; blank = use `PATH` |
| `POPPLER_PATH` | str | `""` | Poppler `bin` dir; blank = use `PATH`. **Overrides `PATH` when set** |
| `HYBRID_ENABLED` | bool | `true` | BM25 + dense fused with RRF |
| `CANDIDATE_K` | int | `20` | Candidates each retriever contributes |
| `RRF_K` | int | `60` | RRF damping constant |
| `RERANK_ENABLED` | bool | `false` | Cross-encoder second pass |
| `RERANK_MODEL` | str | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder id (~90MB) |
| `RERANK_CANDIDATES` | int | `20` | How many candidates reach the reranker |
| `REWRITE_ENABLED` | bool | `false` | LLM query rewriting |
| `REWRITE_MODEL` | str | `""` | Blank = reuse the generation model |
| `MMR_ENABLED` | bool | `false` | Diversity filter |
| `MMR_LAMBDA` | float | `0.7` | 1.0 = pure relevance, 0.0 = pure diversity |

Frontend: `VITE_API_BASE_URL`, default `http://localhost:8000/api`.

> The `HYBRID_ENABLED` default in code is `true` (hybrid was shipped, §18.7)
> while `.env.example` still ships `false` — see §24.1.

### Tuning guidance

| Goal | Change | Cost |
|---|---|---|
| Better exact-identifier matching | `HYBRID_ENABLED=true` | ~2ms/query |
| Better ranking of what was found | `RERANK_ENABLED=true` | ~130ms/query + 90MB model |
| Deeper candidate pool for rerank/MMR | raise `CANDIDATE_K` | slower rerank |
| Favour retriever agreement more | raise `RRF_K` | may bury single-retriever finds |
| Favour single-retriever finds | lower `RRF_K` | reduces fusion to "winner takes all" |
| Fewer near-duplicate results | `MMR_ENABLED=true`, lower `MMR_LAMBDA` | may lower hit-rate on single-answer questions |
| Handle conversational questions | `REWRITE_ENABLED=true` | +1 LLM call (~800ms) per query |
| Larger context per chunk | raise `CHUNK_SIZE` | fewer, coarser chunks; more tokens per call |
| Better boundary-spanning facts | raise `CHUNK_OVERLAP` | more duplication, more storage |

---

## Appendix C — Glossary

**avgdl** — Average document length across the BM25 corpus, in tokens. Used to
normalise for chunk length so long chunks do not win by size alone.

**Bi-encoder** — Embeds question and document *separately*, compares vectors.
Fast, indexable, less accurate. What the dense search uses.

**BM25** — Best Matching 25. A keyword ranking function weighting rare terms
heavily, with term-frequency saturation (`k1`) and length normalisation (`b`).

**candidate_k** — How many candidates the first retrieval stage fetches when a
later stage will re-order. The hard ceiling on what the pipeline can get right.

**Chunk** — A slice of a document that is embedded and retrieved as a unit.
Here: a 1000-word window with 150 words of overlap, scoped to one page.

**Cosine similarity** — Angle-based similarity between vectors, in `[-1, 1]`.
Chroma returns *distance*; `vector_store.query()` converts to similarity.

**Cross-encoder** — Runs `[question] [SEP] [chunk]` through a transformer
jointly. More accurate than a bi-encoder, far too slow for a whole corpus, so
used as a second pass.

**Dense search** — Retrieval by embedding similarity. Matches on meaning.

**Generation failure** — The right chunk *was* in the context and the answer is
still wrong. Fix the prompt, the chunk size, or the model.

**Golden set** — Questions paired with the pages that actually contain their
answers. The ground truth every metric is computed against.

**hit-rate@k** — Fraction of questions where at least one correct chunk was in
the top k. The headline metric.

**HNSW** — Hierarchical Navigable Small World. The approximate nearest-neighbour
index ChromaDB uses.

**HyDE** — Hypothetical Document Embeddings. Generate a plausible *answer*,
embed that, and search with it — document→document similarity instead of
question→document.

**IDF** — Inverse Document Frequency. How rare a term is across the corpus. The
component of BM25 that makes exact-identifier matching work.

**lambda (MMR)** — Balance between relevance and diversity. 1.0 = pure
relevance, 0.0 = pure diversity, 0.7 = the default here.

**MMR** — Maximal Marginal Relevance. Greedy selection penalising similarity to
already-selected results.

**MRR** — Mean Reciprocal Rank. Average of `1/rank` of the first correct chunk.
Sensitive to ranking improvements that hit-rate@k cannot see.

**Open coding** — Qualitative method: describe each failure in one verbatim
sentence *before* imposing categories, then cluster the sentences.

**recall@k** — Fraction of *all* correct chunks that appeared in the top k.
Matters for multi-page answers.

**Rerank** — A second, more expensive scoring pass over a small candidate set.

**Retrieval failure** — The right chunk never reached the LLM. Fix retrieval,
chunking, or the query — **not** the model.

**RRF** — Reciprocal Rank Fusion. Combines ranked lists by
`Σ 1/(k + rank)`, using ranks rather than scores so no normalisation is needed.

**Trace** — The structured record of what every pipeline stage did. Returned
with each query and persisted to `traces.jsonl`.

**Triage** — Classifying a failure as retrieval vs generation, mechanically,
by checking whether a correct chunk was in the top k.

---

## Appendix D — Commit History

| Commit | Date | Summary |
|---|---|---|
| `d140e3b` | 2026-08-27 | Retrieval assistant UI: upload, chat, evaluation, inspection panels |
| `d40edc4` | 2026-08-28 | Fix `generate_answer` error handling; fix candidate filtering in `apply_mmr` |
| `1626a3c` | 2026-08-30 | Refactor styles, add Tailwind configuration |
| `507f6bf` | 2026-08-30 | Custom icon components, improved loading states |
| `18b03c2` | 2026-08-30 | Markdown rendering for assistant responses and inspector answers |
| `078f378` | 2026-09-01 | LLM provider switching; improved error handling |
| `165ac86` | 2026-09-03 | Week 5 error analysis notes: schema audit, verbatim open-coding |
| `43607cd` | 2026-09-05 | Trace dataset generator and replay engine |
| `cdfac10` | 2026-09-05 | Trace logging service for user interactions |
| `38c5388` | 2026-09-05 | `remark-gfm` for GFM tables in ChatPanel and InspectorPanel |
| `5a7c7c4` | 2026-09-05 | Document Chunks feature: chunk retrieval and UI integration |

---

## Closing Note

The thing worth taking from this codebase is not the RAG pipeline — hybrid
search and cross-encoder reranking are well-documented techniques anyone can
implement. It is the **measurement infrastructure around them**:

- A **golden set** keyed on something that survives re-ingestion.
- A **trace** rich enough that when a technique underperforms you can read its
  intermediate output instead of guessing. That is how the reasoning-model
  rewrite bug (§11.5) was caught, and it is why "rewriting doesn't work"
  turned out to be "the rewriter was never emitting a query".
- **Per-request strategy flags**, so seven configurations run against one warm
  index and any delta is attributable to exactly one change.
- A **"still broken" list** printed with the same prominence as the "fixed"
  list, so the analysis stays honest.
- A **seeded random sample** of real traffic, because a curated demo set drifts
  towards the questions the system already answers well (§19.4).

Those five things are what turn *"the app feels better"* into
**88.0% → 96.0% hit-rate@3, +8 points, from one change, and here is the one
question it still does not fix and why.**

