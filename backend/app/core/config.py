from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"

    embedding_model: str = "all-MiniLM-L6-v2"

    chroma_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4

    tesseract_cmd: str = ""
    poppler_path: str = ""

    # --- Week 4: retrieval strategy toggles -------------------------------
    # All three default to OFF so the baseline is exactly last week's app.
    # Turn ON exactly one at a time to attribute a hit-rate change to it.

    # Hybrid search: BM25 keyword search fused with dense vector search.
    hybrid_enabled: bool = True
    # How many candidates each retriever contributes before fusion.
    candidate_k: int = 20
    # Reciprocal Rank Fusion damping constant. 60 is the value from the
    # original RRF paper; it stops rank-1 from dominating outright.
    rrf_k: int = 60

    # Cross-encoder reranking: a second pass that re-scores candidates.
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # How many candidates get fed to the reranker.
    rerank_candidates: int = 20

    # Query rewriting: an LLM cleans up the question before searching.
    rewrite_enabled: bool = False
    rewrite_model: str = ""  # blank = reuse openrouter_model

    # MMR: diversity filter, drops near-duplicate chunks from the results.
    mmr_enabled: bool = False
    mmr_lambda: float = 0.7  # 1.0 = pure relevance, 0.0 = pure diversity

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
