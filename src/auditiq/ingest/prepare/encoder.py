"""Text encoders for the embedding layer of the mapping cascade.

Two kinds, analogous to the legacy implementation:

* ``sbert`` — sentence-transformers (needs the ``[mapping]`` extra).
* ``tfidf`` — scikit-learn char n-gram TF-IDF (needs scikit-learn + numpy).
* ``none``  — no encoder; the cascade runs dictionary-only and falls back to review.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from ...core.taxonomy import Taxonomy

SBERT_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Encoder:
    """Encodes texts to L2-normalised vectors, memoising by text."""

    def __init__(self, kind: str, model: str, fit_texts: Sequence[str]):
        if kind not in ("sbert", "tfidf"):
            raise ValueError(f"unknown encoder kind '{kind}'")
        self.kind = kind
        self.model_name = model
        self._cache: dict[str, np.ndarray] = {}
        if kind == "sbert":
            from sentence_transformers import SentenceTransformer  # lazy

            self.m = SentenceTransformer(model)
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer  # lazy

            self.m = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(list(fit_texts))

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        need = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if need:
            if self.kind == "sbert":
                vectors = self.m.encode(need, normalize_embeddings=True, show_progress_bar=False)
            else:
                from sklearn.preprocessing import normalize  # lazy

                vectors = normalize(self.m.transform(need)).toarray()
            for text, vector in zip(need, vectors):
                self._cache[text] = np.asarray(vector, dtype=float)
        return np.stack([self._cache[t] for t in texts])


def fsli_text(taxonomy: Taxonomy, code: str) -> str:
    """The text representation of an FSLI used for embedding (name + description)."""
    item = taxonomy.get(code)
    if item is None:
        return code
    return f"{item.name}. {item.description}"


def make_encoder(
    kind: str, model: str, taxonomy: Taxonomy
) -> Optional[Encoder]:
    """Build an encoder over the taxonomy texts; ``none`` returns ``None``."""
    if kind in (None, "none"):
        return None
    return Encoder(kind, model, [fsli_text(taxonomy, c) for c in taxonomy.codes])


def tfidf_available() -> bool:
    try:
        import sklearn  # noqa: F401

        return True
    except Exception:
        return False


def sbert_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401

        return True
    except Exception:
        return False


def default_encoder_kind() -> str:
    """Prefer tfidf when scikit-learn is present, else fall back to dictionary-only."""
    if tfidf_available():
        return "tfidf"
    if sbert_available():
        return "sbert"
    return "none"
