# data/tmdb.py — AJOUTE à la fin du fichier

import httpx
from config import API_KEY, BASE_URL   # adapte selon ta config

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