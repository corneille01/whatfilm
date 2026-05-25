import faiss
import numpy as np

index = faiss.IndexFlatL2(384)

movies = []


def add_movie(movie_id, embedding):
    index.add(np.array([embedding]).astype("float32"))
    movies.append(movie_id)



def search(embedding, k=10):
    D, I = index.search(
        np.array([embedding]).astype("float32"),
        k
    )

    return [movies[i] for i in I[0]]