# core/retrieval.py

from data.tmdb import search_candidates


def build_search_query(extraction):
    terms = []
    terms += extraction.get("objets", [])
    terms += extraction.get("actions", [])
    terms += extraction.get("genre", [])
    return " ".join(terms)


async def search_candidates_from_extraction(extraction):

    query = build_search_query(extraction)

    if not query:
        return []

    return await search_candidates(query)