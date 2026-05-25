# data/tmdb.py

import httpx
import os

TMDB_KEY = os.getenv("TMDB_API_KEY")


async def search_candidates(query):

    url = "https://api.themoviedb.org/3/search/multi"

    params = {
        "api_key": TMDB_KEY,
        "query": query,
        "language": "fr-FR"
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()

    return data.get("results", [])[:10]