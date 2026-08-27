from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services import retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The BM25 index lives in memory, so it has to be built from ChromaDB
    # on every boot. Doing it here means the first query is not slow.
    count = retriever.ensure_bm25_index(force=True)
    print(f"[startup] BM25 keyword index built over {count} chunks")
    yield


app = FastAPI(title="RAG Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
