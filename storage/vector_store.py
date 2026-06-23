# storage/vector_store.py

from typing import Any, List

import faiss
import numpy as np


VECTOR_DIMENSION = 384

index = faiss.IndexFlatL2(VECTOR_DIMENSION)

movies: list[Any] = []


def _to_vector(embedding) -> np.ndarray:
    vector = np.array([embedding]).astype("float32")

    if vector.shape[1] != VECTOR_DIMENSION:
        raise ValueError(
            f"Embedding invalide: dimension {vector.shape[1]}, "
            f"attendu {VECTOR_DIMENSION}"
        )

    return vector


def add_movie(movie_id, embedding) -> None:
    vector = _to_vector(embedding)

    index.add(vector)
    movies.append(movie_id)


def search(embedding, k: int = 10) -> List[Any]:
    if index.ntotal == 0:
        return []

    vector = _to_vector(embedding)

    k = min(k, index.ntotal)

    distances, indices = index.search(vector, k)

    results = []

    for i in indices[0]:
        if i == -1:
            continue

        if i < len(movies):
            results.append(movies[i])

    return results


def count() -> int:
    return index.ntotal


def clear() -> None:
    global index, movies

    index = faiss.IndexFlatL2(VECTOR_DIMENSION)
    movies = []