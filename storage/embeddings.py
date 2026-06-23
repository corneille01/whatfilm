# storage/embeddings.py

from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def create_embedding(text: str) -> List[float]:
    if not text:
        return []

    model = get_embedding_model()
    embedding = model.encode(text)

    return embedding.tolist()