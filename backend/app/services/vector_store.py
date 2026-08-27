import uuid

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_dir)

_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=settings.embedding_model
)

_collection = _client.get_or_create_collection(
    name="documents",
    embedding_function=_embedding_fn,
    metadata={"hnsw:space": "cosine"},
)


def add_chunks(doc_id: str, filename: str, chunks: list[dict]) -> int:
    if not chunks:
        return 0

    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {"doc_id": doc_id, "filename": filename, "page": c["page"]} for c in chunks
    ]

    _collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


def query(question: str, top_k: int | None = None) -> list[dict]:
    """Dense semantic search. This is the Week 3 baseline retriever.

    Returns chunk `id` alongside the text so downstream fusion and
    reranking can identify the same chunk coming from two retrievers.
    """
    top_k = top_k or settings.top_k
    results = _collection.query(query_texts=[question], n_results=top_k)

    matches = []
    ids = results.get("ids") or [[]]
    docs = results.get("documents") or [[]]
    metas = results.get("metadatas") or [[]]
    dists = results.get("distances") or [[]]

    for cid, text, meta, dist in zip(ids[0], docs[0], metas[0], dists[0]):
        matches.append(
            {
                "id": cid,
                "text": text,
                "filename": meta.get("filename"),
                "page": meta.get("page"),
                "doc_id": meta.get("doc_id"),
                # Chroma returns cosine *distance*; convert to similarity so
                # bigger always means better, consistently across retrievers.
                "score": 1 - dist,
            }
        )
    return matches


def get_all_chunks() -> list[dict]:
    """Every chunk in the collection, used to build the BM25 index."""
    data = _collection.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []

    records = []
    for cid, text, meta in zip(ids, docs, metas):
        meta = meta or {}
        records.append(
            {
                "id": cid,
                "text": text or "",
                "filename": meta.get("filename"),
                "page": meta.get("page"),
                "doc_id": meta.get("doc_id"),
            }
        )
    return records


def get_embeddings(ids: list[str]) -> dict[str, list[float]]:
    """Fetch stored embeddings for specific chunk ids (used by MMR)."""
    if not ids:
        return {}
    data = _collection.get(ids=ids, include=["embeddings"])
    out: dict[str, list[float]] = {}
    got_ids = data.get("ids") or []
    embs = data.get("embeddings")
    if embs is None:
        return {}
    for cid, emb in zip(got_ids, embs):
        if emb is not None:
            out[cid] = list(emb)
    return out


def embed_query(text: str) -> list[float]:
    """Embed an arbitrary string with the same model as the corpus."""
    return list(_embedding_fn([text])[0])


def list_documents() -> list[dict]:
    data = _collection.get(include=["metadatas"])
    seen: dict[str, dict] = {}
    for meta in data.get("metadatas", []):
        doc_id = meta.get("doc_id")
        if doc_id not in seen:
            seen[doc_id] = {"doc_id": doc_id, "filename": meta.get("filename"), "chunks": 0}
        seen[doc_id]["chunks"] += 1
    return list(seen.values())


def delete_document(doc_id: str) -> None:
    _collection.delete(where={"doc_id": doc_id})


def new_doc_id() -> str:
    return uuid.uuid4().hex
