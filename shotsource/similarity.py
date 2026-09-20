"""Caption-to-shot-description similarity via sentence-transformers.

sentence-transformers (and its torch dependency) is imported lazily inside
the model property, not at module load time, so the rest of shotsource -
and its tests - don't need it installed unless a similarity score is
actually requested.
"""
from __future__ import annotations


class CaptionSimilarityScorer:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _model_instance(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def score(self, shot_description: str, caption: str) -> float:
        """Cosine similarity between the shot description and a
        candidate's title/caption, clamped to [0, 1] (embeddings can be
        anti-correlated, but a negative match is scored the same as no
        match for ranking purposes). Returns 0.0 for an empty caption
        rather than calling the model on it."""
        if not caption or not caption.strip():
            return 0.0
        model = self._model_instance()
        embeddings = model.encode([shot_description, caption], normalize_embeddings=True)
        similarity = float(embeddings[0] @ embeddings[1])
        return max(0.0, min(1.0, similarity))
