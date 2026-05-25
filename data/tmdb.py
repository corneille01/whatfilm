# data/tmdb.py

import httpx
import os

TMDB_KEY = os.getenv("TMDB_API_KEY")

async def search_candidates(query, lang="en"):
    url = "https://api.themoviedb.org/3/search/multi"
    
    # Mapping des langues pour TMDB
    lang_map = {
        "fr": "fr-FR",
        "en": "en-US",
        "es": "es-ES",
        "zh": "zh-CN",
        "de": "de-DE"
    }
    
    # Si la langue n'est pas dans le mapping, on utilise l'anglais par défaut
    tmdb_lang = lang_map.get(lang, "en-US")

    params = {
        "api_key": TMDB_KEY,
        "query": query,
        "language": tmdb_lang
    }

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()

    return data.get("results", [])[:10]