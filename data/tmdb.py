import os
import httpx

# TMDB settings – adapte si nécessaire (utilise les variables d'environnement)
API_KEY = os.getenv("TMDB_API_KEY", "ta_cle_tmdb")
BASE_URL = "https://api.themoviedb.org/3"

# Cache des genres pour limiter les appels
_genre_cache = {}

# ── Helpers ─────────────────────────────────────────────────────────
LANG_MAP = {
    "fr": "fr-FR",
    "en": "en-US",
    "es": "es-ES",
    "de": "de-DE",
    "zh": "zh-CN",
}

def _tmdb_lang(lang: str) -> str:
    return LANG_MAP.get(lang, "fr-FR")

# ── Recherche films ─────────────────────────────────────────────────
async def search_candidates(query: str, lang: str = "fr"):
    """Recherche de films TMDB."""
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key": API_KEY,
        "query": query,
        "language": _tmdb_lang(lang),
        "page": 1,
        "include_adult": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])

# ── Recherche séries TV ─────────────────────────────────────────────
async def search_tv_candidates(query: str, lang: str = "fr"):
    """Recherche de séries TV."""
    url = f"{BASE_URL}/search/tv"
    params = {
        "api_key": API_KEY,
        "query": query,
        "language": _tmdb_lang(lang),
        "page": 1,
        "include_adult": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])

# ── Détails d’un film ───────────────────────────────────────────────
async def get_movie_details(movie_id: int, lang: str = "fr"):
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

# ── Détails d’une série TV ──────────────────────────────────────────
async def get_tv_details(tv_id: int, lang: str = "fr"):
    url = f"{BASE_URL}/tv/{tv_id}"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

# ── Liste des genres ────────────────────────────────────────────────
async def get_genre_list(lang: str = "fr"):
    """Retourne la liste des genres de films (avec cache)."""
    tmdb_lang = _tmdb_lang(lang)
    if tmdb_lang in _genre_cache:
        return _genre_cache[tmdb_lang]

    url = f"{BASE_URL}/genre/movie/list"
    params = {"api_key": API_KEY, "language": tmdb_lang}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        genres = resp.json().get("genres", [])
        _genre_cache[tmdb_lang] = genres
        return genres;


async def search_person(name: str, lang: str = "fr") -> dict | None:
    """Cherche un acteur/réalisateur par nom."""
    url = f"{BASE_URL}/search/person"
    params = {
        "api_key": API_KEY,
        "query": name,
        "language": _tmdb_lang(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


async def get_person_credits(person_id: int, lang: str = "fr") -> list:
    """Retourne tous les films d'un acteur."""
    url = f"{BASE_URL}/person/{person_id}/combined_credits"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cast = data.get("cast", [])
        # Trier par popularité
        return sorted(cast, key=lambda x: x.get("popularity", 0), reverse=True)

# ── Discover par genre ──────────────────────────────────────────────
async def discover_by_genre(genre_id: int, lang: str = "fr", page: int = 1, media_type: str = "movie"):
    """Découverte de films/séries par genre."""
    endpoint = "discover/movie" if media_type != "tv" else "discover/tv"
    url = f"{BASE_URL}/{endpoint}"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
        "with_genres": str(genre_id),
        "page": page,
        "sort_by": "popularity.desc",
        "include_adult": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "results": data.get("results", []),
            "page": data.get("page", page),
            "total_pages": data.get("total_pages", 1),
            "total_results": data.get("total_results", 0),
        }

# ── Trending ────────────────────────────────────────────────────────
async def get_trending(lang: str = "fr", media_type: str = "movie"):
    """Tendances films ou séries."""
    url = f"{BASE_URL}/trending/{media_type}/week"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])

# ── Détails d’une saison (NOUVEAU) ─────────────────────────────────
async def get_season_details(series_id: int, season_number: int, lang: str = "fr") -> dict:
    """
    Récupère les épisodes d'une saison via TMDB.
    Endpoint: GET /tv/{series_id}/season/{season_number}
    """
    url = f"{BASE_URL}/tv/{series_id}/season/{season_number}"
    params = {
        "api_key": API_KEY,
        "language": _tmdb_lang(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()