"""BM25 keyword search — pure Python, no extra dependencies.

WHY THIS EXISTS
---------------
Dense (embedding) search matches on *meaning*. That is great for
"how does restocking work?" and bad for "what does BILL-RESTOCK mean?",
because an embedding model squashes a rare token like BILL-RESTOCK into
roughly the same vector region as RESTOCK-ONLY and BILL-ONLY. They are
semantically near-identical and operationally opposite.

BM25 matches on *exact words*, and it weights rare words heavily. A token
that appears in only one chunk out of 25 gets a large IDF, so the chunk
that literally contains "S0A59667" wins outright. That is precisely the
failure mode dense search cannot fix by itself.

THE FORMULA
-----------
For a query Q and document D:

    score(D, Q) = sum over each query term q of
                    IDF(q) * ( f(q,D) * (k1 + 1) )
                             ------------------------------------
                             ( f(q,D) + k1 * (1 - b + b * |D|/avgdl) )

  f(q,D)  how many times term q appears in document D  (term frequency)
  |D|     length of D in tokens
  avgdl   average document length across the corpus
  IDF(q)  how rare q is across the corpus -- the important part
  k1=1.5  term-frequency saturation: the 10th occurrence of a word adds
          far less than the 2nd. Without this, keyword spam would win.
  b=0.75  length normalisation: stops long chunks from winning just by
          being long and therefore containing more words.
"""

import math
import re
import threading

# Split on anything that is not a letter, digit, hyphen or underscore.
# Hyphen and underscore are DELIBERATELY kept as word characters so that
# "BILL-RESTOCK", "cim_", "320-32-36" and "-L" survive tokenisation as
# single searchable units. A naive \w+ tokeniser would shatter
# "BILL-RESTOCK" into "bill" + "restock" and destroy the exact-match
# advantage that is the entire reason we added BM25.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")

K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase and split text into BM25 terms.

    Also emits sub-tokens for hyphenated compounds, so that a query for
    "restock" still partially matches a chunk containing "BILL-RESTOCK",
    while an exact query for "BILL-RESTOCK" still gets the full-token hit.
    """
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


class BM25Index:
    """An in-memory BM25 index over the chunk corpus.

    Rebuilt from ChromaDB whenever documents are added or deleted. The
    corpus here is small (tens to thousands of chunks), so a full rebuild
    costs milliseconds and avoids incremental-update bugs.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: list[str] = []
        self._meta: list[dict] = []
        self._texts: list[str] = []
        self._tf: list[dict[str, int]] = []
        self._doc_len: list[int] = []
        self._df: dict[str, int] = {}
        self._avgdl: float = 0.0
        self._built = False

    # -- building ---------------------------------------------------------

    def build(self, records: list[dict]) -> None:
        """Build the index. `records` = [{id, text, filename, page, doc_id}]."""
        with self._lock:
            self._ids = []
            self._meta = []
            self._texts = []
            self._tf = []
            self._doc_len = []
            self._df = {}

            for rec in records:
                tokens = tokenize(rec["text"])
                tf: dict[str, int] = {}
                for t in tokens:
                    tf[t] = tf.get(t, 0) + 1

                self._ids.append(rec["id"])
                self._texts.append(rec["text"])
                self._meta.append(
                    {
                        "filename": rec.get("filename"),
                        "page": rec.get("page"),
                        "doc_id": rec.get("doc_id"),
                    }
                )
                self._tf.append(tf)
                self._doc_len.append(len(tokens))

                for term in tf:
                    self._df[term] = self._df.get(term, 0) + 1

            n = len(self._doc_len)
            self._avgdl = (sum(self._doc_len) / n) if n else 0.0
            self._built = True

    @property
    def size(self) -> int:
        return len(self._ids)

    def is_built(self) -> bool:
        return self._built

    # -- scoring ----------------------------------------------------------

    def _idf(self, term: str) -> float:
        """Smoothed inverse document frequency.

        A term in 1 of 25 chunks scores high; a term in all 25 scores ~0.
        The +0.5/+1.0 smoothing keeps this positive and finite even for
        terms that appear in every document.
        """
        n = len(self._doc_len)
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int) -> list[dict]:
        """Return the top_k chunks by BM25 score, best first."""
        with self._lock:
            if not self._built or not self._ids:
                return []

            q_terms = tokenize(query)
            if not q_terms:
                return []

            # Precompute IDF once per distinct query term.
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

            out = []
            for score, i in scored[:top_k]:
                out.append(
                    {
                        "id": self._ids[i],
                        "text": self._texts[i],
                        "filename": self._meta[i]["filename"],
                        "page": self._meta[i]["page"],
                        "doc_id": self._meta[i]["doc_id"],
                        "score": score,
                    }
                )
            return out


# Module-level singleton, mirroring how vector_store holds one collection.
index = BM25Index()
