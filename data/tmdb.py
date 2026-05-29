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


async def search_tv_candidates(query: str, lang: str = "fr") -> list:
    """Recherche dédiée aux séries TV."""
    try:
        data = await _get("/search/tv", {"query": query, "language": lang, "include_adult": False})
        results = data.get("results", [])
        # Ajouter media_type pour cohérence avec search_multi
        for r in results:
            r["media_type"] = "tv"
        return results[:10]
    except Exception as e:
        print(f"search_tv_candidates error: {e}")
        return []


async def get_movie_details(movie_id: int, lang: str = "fr") -> dict:
    """
    Détails complets d'un film avec tous les appends.
    Retourne un dict unifié avec tous les champs TMDB enrichis.
    """
    append = "credits,videos,watch/providers,similar,recommendations,images,keywords,release_dates,external_ids"

    try:
        details = await _get(f"/movie/{movie_id}", {"language": lang, "append_to_response": append})
        details["_media_type"] = "movie"
        return details
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Essayer comme TV series en fallback
            try:
                details = await _get(f"/tv/{movie_id}", {"language": lang, "append_to_response": append})
                details["_media_type"] = "tv"
                return details
            except Exception as e2:
                print(f"get_movie_details TV fallback error: {e2}")
                return {}
        else:
            print(f"get_movie_details error: {e}")
            return {}
    except Exception as e:
        print(f"get_movie_details error: {e}")
        return {}


async def get_tv_details(tv_id: int, lang: str = "fr") -> dict:
    """
    Détails complets d'une série TV avec tous les appends.
    Endpoint dédié /tv/{id} pour éviter les 404 silencieux.
    """
    append = "credits,videos,watch/providers,similar,recommendations,images,keywords,content_ratings,external_ids"

    try:
        details = await _get(f"/tv/{tv_id}", {"language": lang, "append_to_response": append})
        details["_media_type"] = "tv"
        # Normaliser certains champs pour cohérence avec les films
        if "name" in details and "title" not in details:
            details["title"] = details["name"]
        if "first_air_date" in details and "release_date" not in details:
            details["release_date"] = details["first_air_date"]
        return details
    except Exception as e:
        print(f"get_tv_details error: {e}")
        return {}


async def get_genre_list(lang: str = "fr", media_type: str = "movie") -> list:
    """Liste des genres TMDB dans la langue demandée (movie ou tv)."""
    try:
        endpoint = f"/genre/{media_type}/list"
        data = await _get(endpoint, {"language": lang})
        return data.get("genres", [])
    except Exception as e:
        print(f"get_genre_list error: {e}")
        return []


async def discover_by_genre(genre_id: int, lang: str = "fr", page: int = 1, media_type: str = "movie") -> dict:
    """
    Découverte des films ou séries par genre.
    Supporte media_type='movie' ou 'tv'.
    Retourne results + total_pages pour la pagination.
    """
    try:
        endpoint = f"/discover/{media_type}"
        params = {
            "language": lang,
            "sort_by": "popularity.desc",
            "with_genres": genre_id,
            "page": page,
            "include_adult": False,
        }
        # vote_count minimum uniquement pour les films (les séries ont moins de votes)
        if media_type == "movie":
            params["vote_count.gte"] = 50
        else:
            params["vote_count.gte"] = 20

        data = await _get(endpoint, params)
        results = data.get("results", [])

        # Ajouter media_type pour cohérence
        for r in results:
            if "media_type" not in r:
                r["media_type"] = media_type

        return {
            "results": results,
            "total_pages": min(data.get("total_pages", 1), 500),  # TMDB cap à 500
            "total_results": data.get("total_results", 0),
            "page": page,
        }
    except Exception as e:
        print(f"discover_by_genre error: {e}")
        return {"results": [], "total_pages": 1, "total_results": 0, "page": 1}


async def get_trending(lang: str = "fr", media_type: str = "all") -> list:
    """
    Films/Séries tendances de la semaine.
    media_type: 'all', 'movie', ou 'tv'
    """
    try:
        data = await _get(f"/trending/{media_type}/week", {"language": lang})
        results = data.get("results", [])
        # Filtrer les personnes si all
        if media_type == "all":
            results = [r for r in results if r.get("media_type") in ("movie", "tv")]
        else:
            # Ajouter media_type explicitement
            for r in results:
                if "media_type" not in r:
                    r["media_type"] = media_type
        return results[:20]
    except Exception as e:
        print(f"get_trending error: {e}")
        # Fallback: top films populaires
        try:
            data = await _get("/movie/popular", {"language": lang})
            results = data.get("results", [])
            for r in results:
                r["media_type"] = "movie"
            return results[:20]
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