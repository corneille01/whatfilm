import httpx
import os

TMDB_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
LANG_MAP = {"fr": "fr-FR", "en": "en-US", "es": "es-ES", "zh": "zh-CN", "de": "de-DE"}

async def search_candidates(query, lang="en"):
    url = f"{BASE_URL}/search/multi"
    params = {"api_key": TMDB_KEY, "query": query, "language": LANG_MAP.get(lang, "en-US")}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        return r.json().get("results", [])[:10]

async def get_movie_details(movie_id, lang="fr"):
    url = f"{BASE_URL}/movie/{movie_id}"
    # Ajout de 'credits' pour les acteurs
    params = {"api_key": TMDB_KEY, "language": LANG_MAP.get(lang, "en-US"), "append_to_response": "watch/providers,videos,similar,credits"}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        return r.json()

async def get_genre_list(lang="fr"):
    url = f"{BASE_URL}/genre/movie/list"
    params = {"api_key": TMDB_KEY, "language": LANG_MAP.get(lang, "en-US")}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        return r.json().get("genres", [])

async def discover_by_genre(genre_id, lang="fr", page=1):
    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_KEY, 
        "language": LANG_MAP.get(lang, "en-US"), 
        "with_genres": genre_id, 
        "sort_by": "popularity.desc",
        "page": page
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()
        return {"results": data.get("results", []), "total_pages": data.get("total_pages", 1)}

async def get_trending(lang="fr", page=1):
    url = f"{BASE_URL}/trending/movie/week"
    params = {"api_key": TMDB_KEY, "language": LANG_MAP.get(lang, "en-US"), "page": page}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        data = r.json()
        return {"results": data.get("results", []), "total_pages": data.get("total_pages", 1)}