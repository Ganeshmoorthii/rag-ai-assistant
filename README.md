# RAG Assistant

Full-stack Retrieval-Augmented Generation app: upload PDFs, ask questions, get answers grounded in your documents with source citations.

**Stack**
- Backend: FastAPI + ChromaDB (vector store) + Sentence-Transformers (local embeddings) + OpenRouter (LLM generation)
- Frontend: React + Vite

## Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then edit .env and add your OPENROUTER_API_KEY
uvicorn app.main:app --reload --port 8000
```

Get an OpenRouter API key at https://openrouter.ai/keys. Set `OPENROUTER_MODEL` in `.env` to any model id available on OpenRouter (e.g. `anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini`, `meta-llama/llama-3.1-8b-instruct`).

## Frontend setup

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open http://localhost:5173.

## How it works

1. Upload a PDF — the backend extracts text per page, splits it into overlapping word chunks, embeds each chunk locally with `sentence-transformers/all-MiniLM-L6-v2`, and stores them in a persistent ChromaDB collection.
2. Ask a question — the backend embeds the question, retrieves the top-K most similar chunks from ChromaDB, and sends them as context to the LLM via OpenRouter.
3. The answer is returned along with the source chunks (filename, page, similarity score) used to generate it.

## Retrieval debugging (Week 4)

The app can now tell you **which half of the pipeline is broken** — whether it
fetched the wrong document, or fetched the right one and answered badly — and
measure any retrieval change with a before/after number.

See **[RETRIEVAL_DEBUGGING.md](RETRIEVAL_DEBUGGING.md)** for the full writeup,
results, and concept notes.

Headline result on this repo's own PDFs (25 golden questions, `top_k=3`):

| config | hit@1 | hit@3 | MRR |
|---|---|---|---|
| baseline (dense only) | 72.0% | 88.0% | 0.8000 |
| hybrid (BM25 + RRF) | 80.0% | **96.0%** | 0.8733 |
| rerank (cross-encoder) | **88.0%** | **96.0%** | **0.9200** |

Three UI tabs: **Chat** (as before), **Inspector** (question / retrieved
chunks / answer side by side, plus a retrieval-vs-generation verdict), and
**Measurement** (run the golden set, compare two configs).

```bash
cd backend
.venv/Scripts/python -m eval.run_eval --sweep --save
.venv/Scripts/python -m eval.run_eval --compare baseline rerank
```

## API

- `POST /api/documents` — upload a PDF (multipart form, field `file`)
- `GET /api/documents` — list ingested documents
- `DELETE /api/documents/{doc_id}` — remove a document and its chunks
- `POST /api/query` — `{ question, top_k?, hybrid?, rerank?, rewrite?, mmr?, hyde?, retrieval_only? }` → `{ answer, sources, trace }`
- `POST /api/triage` — `{ question, expected: [{filename, page}] }` → retrieval-vs-generation verdict
- `POST /api/evaluate` — `{ config }` → hit-rate@k, recall@k, MRR over the golden set
- `GET /api/golden-set` · `GET /api/configs` · `GET /api/retrieval-settings`

## Config (`backend/.env`)

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | required for generation |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | model id on OpenRouter |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | local embedding model |
| `CHROMA_DIR` | `./data/chroma` | vector DB persistence path |
| `UPLOAD_DIR` | `./data/uploads` | uploaded PDF storage |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | chunking (in words) |
| `TOP_K` | `4` | chunks retrieved per query |
| `HYBRID_ENABLED` | `false` | BM25 + dense, fused with RRF |
| `CANDIDATE_K` / `RRF_K` | `20` / `60` | candidates per retriever; RRF damping |
| `RERANK_ENABLED` | `false` | cross-encoder second pass |
| `REWRITE_ENABLED` | `false` | LLM query rewriting |
| `MMR_ENABLED` / `MMR_LAMBDA` | `false` / `0.7` | diversity filter |

All four strategy toggles default to **off**, so the default app is the Week 3
baseline. Turn on exactly one at a time to attribute a change.
