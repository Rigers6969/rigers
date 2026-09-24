"""Caption-to-shot-description similarity via sentence-transformers.

sentence-transformers (and its torch dependency) is imported lazily inside
the model property, not at module load time, so the rest of shotsource -
and its tests - don't need it installed unless a similarity score is
actually requested.
"""
from __future__ import annotations

# Loading a SentenceTransformer model (disk read + torch init) is a real
# fixed cost - a few seconds at least - that's the same whether the run
# has 2 shots or 40. run_pipeline() builds a fresh CaptionSimilarityScorer
# every call, but web_server.py's Flask process stays alive across many
# runs, so without this cache every single production run paid that fixed
# cost again from scratch - proportionally brutal for a short 30-40s
# video, where it can dwarf the actual work. Keyed by model name so a
# custom config with a different embedding_model still gets its own load.
_MODEL_CACHE: dict[str, object] = {}


class CaptionSimilarityScorer:
    def __init__(self, model_name: str):
        self._model_name = model_name

    def _model_instance(self):
        if self._model_name not in _MODEL_CACHE:
            from sentence_transformers import SentenceTransformer

            _MODEL_CACHE[self._model_name] = SentenceTransformer(self._model_name)
        return _MODEL_CACHE[self._model_name]

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
