"""
data/tmdb.py — Client TMDB enrichi
"""
import httpx
import os

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
BASE = "https://api.themoviedb.org/3"

HEADERS = {
    "accept": "application/json",
}

async def _get(path: str, params: dict = None) -> dict:
    """Helper GET avec gestion d'erreur."""
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{BASE}{path}", params=params, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def search_candidates(query: str, lang: str = "fr") -> list:
    """Recherche multi (films + séries + anime)."""
    try:
        data = await _get("/search/multi", {"query": query, "language": lang, "include_adult": False})
        results = data.get("results", [])
        # Filtrer: garder movies et TV, exclure les personnes
        filtered = [r for r in results if r.get("media_type") in ("movie", "tv")]
        return filtered[:10]
    except Exception as e:
        print(f"search_candidates error: {e}")
        return []


async def get_movie_details(movie_id: int, lang: str = "fr") -> dict:
    """
    Détails complets d'un film/série avec tous les appends.
    Retourne un dict unifié avec tous les champs TMDB enrichis.
    """
    # On essaie d'abord en movie, puis en tv si ça échoue
    append = "credits,videos,watch/providers,similar,recommendations,images,keywords,release_dates,external_ids"

    details = {}
    media_type = "movie"

    try:
        details = await _get(f"/movie/{movie_id}", {"language": lang, "append_to_response": append})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Essayer comme TV series
            try:
                details = await _get(f"/tv/{movie_id}", {"language": lang, "append_to_response": append})
                media_type = "tv"
            except Exception as e2:
                print(f"get_movie_details TV error: {e2}")
                return {}
        else:
            print(f"get_movie_details error: {e}")
            return {}
    except Exception as e:
        print(f"get_movie_details error: {e}")
        return {}

    details["_media_type"] = media_type
    return details


async def get_genre_list(lang: str = "fr") -> list:
    """Liste des genres TMDB dans la langue demandée."""
    try:
        data = await _get("/genre/movie/list", {"language": lang})
        return data.get("genres", [])
    except Exception as e:
        print(f"get_genre_list error: {e}")
        return []


async def discover_by_genre(genre_id: int, lang: str = "fr", page: int = 1) -> dict:
    """
    Découverte des films par genre.
    Retourne results + total_pages pour la pagination.
    """
    try:
        data = await _get("/discover/movie", {
            "language": lang,
            "sort_by": "popularity.desc",
            "with_genres": genre_id,
            "page": page,
            "include_adult": False,
            "vote_count.gte": 50,
        })
        return {
            "results": data.get("results", []),
            "total_pages": min(data.get("total_pages", 1), 500),  # TMDB cap à 500
            "total_results": data.get("total_results", 0),
            "page": page,
        }
    except Exception as e:
        print(f"discover_by_genre error: {e}")
        return {"results": [], "total_pages": 1, "total_results": 0, "page": 1}


async def get_trending(lang: str = "fr") -> list:
    """
    Films/Séries tendances de la semaine.
    FIX: utilise /trending/all/week qui fonctionne sans paramètre genre.
    """
    try:
        data = await _get("/trending/all/week", {"language": lang})
        results = data.get("results", [])
        # Filtrer les personnes
        filtered = [r for r in results if r.get("media_type") in ("movie", "tv")]
        return filtered[:20]
    except Exception as e:
        print(f"get_trending error: {e}")
        # Fallback: top films populaires
        try:
            data = await _get("/movie/popular", {"language": lang})
            return data.get("results", [])[:20]
        except Exception as e2:
            print(f"get_trending fallback error: {e2}")
            return []


async def get_person_details(person_id: int, lang: str = "fr") -> dict:
    """Biographie et filmographie d'un acteur."""
    try:
        return await _get(f"/person/{person_id}", {
            "language": lang,
            "append_to_response": "movie_credits,tv_credits,images"
        })
    except Exception as e:
        print(f"get_person_details error: {e}")
        return {}


async def search_candidates_by_person(actor_name: str, lang: str = "fr") -> list:
    """Recherche par nom d'acteur, retourne ses films."""
    try:
        data = await _get("/search/person", {"query": actor_name, "language": lang})
        persons = data.get("results", [])
        if not persons:
            return []
        person_id = persons[0]["id"]
        person = await get_person_details(person_id, lang)
        movies = person.get("movie_credits", {}).get("cast", [])
        return sorted(movies, key=lambda x: x.get("popularity", 0), reverse=True)[:10]
    except Exception as e:
        print(f"search_candidates_by_person error: {e}")
        return []