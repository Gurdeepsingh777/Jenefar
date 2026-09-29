from __future__ import annotations

import math
from typing import Iterable


class SemanticEmbedder:
    """Optional local sentence-transformers embeddings with safe lexical fallback."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self.available = False

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self.available = True
        except Exception:
            self._model = None
            self.available = False

    def encode(self, text: str) -> list[float] | None:
        if not self.available or self._model is None:
            return None
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]

    @staticmethod
    def cosine(left: Iterable[float], right: Iterable[float]) -> float:
        a = list(left)
        b = list(right)
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
