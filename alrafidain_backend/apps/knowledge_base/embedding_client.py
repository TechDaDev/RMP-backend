"""
Embedding client for the Knowledge Base.

Uses sentence-transformers to produce normalized float embeddings.
The client is lazy-loaded to avoid importing heavy ML libraries at
startup; tests should mock this module rather than loading a real model.
"""

from __future__ import annotations

import numpy as np
from django.conf import settings


class LocalEmbeddingClient:
    """Thin wrapper around a SentenceTransformer model."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or getattr(
            settings, "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self._model = None  # lazy-loaded

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """Return a normalized embedding for a single text string."""
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return normalized embeddings for a list of text strings."""
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [arr.tolist() for arr in np.asarray(embeddings)]


_default_client: LocalEmbeddingClient | None = None


def get_default_embedding_client() -> LocalEmbeddingClient:
    """Return the module-level singleton embedding client."""
    global _default_client  # noqa: PLW0603
    if _default_client is None:
        _default_client = LocalEmbeddingClient()
    return _default_client
