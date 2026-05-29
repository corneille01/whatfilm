# ══════════════════════════════════════════════════════════════
# PATCH app.py — Ajouter cette route APRÈS la route /movie/{movie_id}
# ══════════════════════════════════════════════════════════════

@app.get("/tv/{series_id}/season/{season_number}")
async def get_season(series_id: int, season_number: int, lang: str = "fr"):
    """Retourne les détails d'une saison avec ses épisodes."""
    try:
        from data.tmdb import get_season_details
        data = await get_season_details(series_id, season_number, lang)
        return data
    except Exception as e:
        return {"error": str(e), "episodes": []}


# ══════════════════════════════════════════════════════════════
# PATCH data/tmdb.py — Ajouter cette fonction dans tmdb.py
# ══════════════════════════════════════════════════════════════

async def get_season_details(series_id: int, season_number: int, lang: str = "fr") -> dict:
    """
    Récupère les épisodes d'une saison via TMDB.
    Endpoint: GET /tv/{series_id}/season/{season_number}
    """
    lang_map = {
        "fr": "fr-FR", "en": "en-US", "es": "es-ES",
        "de": "de-DE", "zh": "zh-CN",
    }
    tmdb_lang = lang_map.get(lang, "fr-FR")

    url = f"{BASE_URL}/tv/{series_id}/season/{season_number}"
    params = {"api_key": API_KEY, "language": tmdb_lang}

    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    # Retourne: { id, name, air_date, episodes: [{...}, ...], poster_path, ... }
    # Chaque épisode contient: episode_number, name, overview, air_date, still_path, vote_average


# ══════════════════════════════════════════════════════════════
# PATCH data/tmdb.py — get_tv_details doit inclure seasons[]
# 
# Vérifier que get_tv_details fait bien:
#   append_to_response = "credits,videos,similar,recommendations,watch/providers"
# et que TMDB retourne bien seasons[] dans la réponse de base /tv/{id}
# (TMDB inclut seasons[] automatiquement dans /tv/{id}, pas besoin d'append)
# ══════════════════════════════════════════════════════════════