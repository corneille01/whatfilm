"""
core/filming_catalogue.py  —  Catalogue lieux de tournage v5

Architecture :
  - Le catalogue est chargé depuis un fichier JSON pré-généré (catalogue_filming.json)
  - Ce fichier est généré en local avec build_catalogue_local.py et commité dans le repo
  - PLUS de requêtes Wikidata au runtime → plus de blocages IP cloud
  - Enrichissement TMDB (poster, note) fait au démarrage sur les films avec tmdb_id
  - Refresh TMDB toutes les 24h (léger, pas de Wikidata)
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TMDB_BASE  = "https://api.themoviedb.org/3"
TMDB_KEY   = os.getenv("TMDB_API_KEY", "")

# Chemin vers le catalogue JSON pré-généré (commité dans le repo)
CATALOGUE_JSON = os.path.join(
    os.path.dirname(__file__), "..", "catalogue_filming.json"
)
# Fallback : chercher à la racine du projet
CATALOGUE_JSON_ALT = os.path.join(
    os.path.dirname(__file__), "catalogue_filming.json"
)

TMDB_REFRESH = 3600 * 24   # ré-enrichit TMDB toutes les 24h

# ---------------------------------------------------------------------------
# État global en RAM
# ---------------------------------------------------------------------------
_catalogue: list[dict] = []
_catalogue_loaded_at: float = 0.0
_catalogue_loading: bool = False
_catalogue_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _catalogue_lock
    if _catalogue_lock is None:
        _catalogue_lock = asyncio.Lock()
    return _catalogue_lock


# ---------------------------------------------------------------------------
# Chargement depuis JSON
# ---------------------------------------------------------------------------
def _load_json_catalogue() -> list[dict]:
    """Charge le catalogue depuis le fichier JSON pré-généré."""
    for path in [CATALOGUE_JSON, CATALOGUE_JSON_ALT]:
        path = os.path.abspath(path)
        if os.path.exists(path):
            logger.info("Catalogue: chargement depuis %s", path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            logger.info("Catalogue: %s films chargés depuis JSON", len(data))
            return data
    logger.warning("Catalogue: catalogue_filming.json introuvable — fallback statique")
    return []


async def _load_catalogue_bg() -> None:
    global _catalogue, _catalogue_loaded_at, _catalogue_loading

    lock = _get_lock()
    async with lock:
        if _catalogue_loading:
            return
        _catalogue_loading = True

    try:
        # 1. Charger le JSON (instantané)
        films = _load_json_catalogue()

        if not films:
            films = copy.deepcopy(_FALLBACK)
            logger.warning("Catalogue: utilisation du fallback statique (3 films)")
        
        # 2. Enrichissement TMDB en arrière-plan (posters, notes)
        if TMDB_KEY and films:
            logger.info("Catalogue: enrichissement TMDB pour %s films...", len(films))
            await _enrich_tmdb_batch(films)
            logger.info("Catalogue: enrichissement TMDB terminé")

        async with lock:
            _catalogue = films
            _catalogue_loaded_at = time.time()
            _catalogue_loading = False

        logger.info("Catalogue v5: PRÊT — %s films en RAM", len(_catalogue))

    except Exception as exc:
        logger.error("Catalogue: erreur chargement: %s", exc)
        async with lock:
            _catalogue_loading = False


async def ensure_catalogue_loaded() -> None:
    now = time.time()
    if _catalogue and (now - _catalogue_loaded_at) < TMDB_REFRESH:
        return
    if _catalogue_loading:
        return
    asyncio.create_task(_load_catalogue_bg())


# ---------------------------------------------------------------------------
# Enrichissement TMDB
# ---------------------------------------------------------------------------
async def _enrich_tmdb_batch(films: list[dict], lang: str = "fr") -> None:
    if not TMDB_KEY:
        return

    async def fetch_one(film: dict) -> None:
        tmdb_id = film.get("tmdb_id")
        if not tmdb_id:
            return
        mtype = film.get("media_type", "movie")
        ep = f"/tv/{tmdb_id}" if mtype == "tv" else f"/movie/{tmdb_id}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"{TMDB_BASE}{ep}",
                    params={"api_key": TMDB_KEY, "language": lang},
                )
                if r.status_code == 200:
                    d = r.json()
                    film["poster_path"]  = d.get("poster_path")
                    film["vote_average"] = d.get("vote_average")
                    film["vote_count"]   = d.get("vote_count")
                    film["overview"]     = d.get("overview", "")
                    title = d.get("title") or d.get("name")
                    if title:
                        film["title"] = title
                        film["_title_lower"] = title.lower()
        except Exception as exc:
            logger.debug("TMDB enrich %s: %s", tmdb_id, exc)

    for i in range(0, len(films), 20):
        await asyncio.gather(*[fetch_one(f) for f in films[i:i + 20]])
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# Fallback statique
# ---------------------------------------------------------------------------
_FALLBACK: list[dict] = [
    {
        "wikidata_id": "Q471", "title": "The Dark Knight",
        "tmdb_id": 155, "media_type": "movie", "year": 2008,
        "poster_path": None, "vote_average": 9.0, "vote_count": 30000,
        "location_count": 1, "countries": ["Royaume-Uni"],
        "_title_lower": "the dark knight", "_countries_lower": ["royaume-uni"],
        "primary_location": {"name": "Londres", "lat": 51.5074, "lng": -0.1278,
                             "country": "Royaume-Uni", "wikidata_id": "Q84"},
        "locations": [{"wikidata_id": "Q84", "name": "Londres",
                       "country": "Royaume-Uni", "lat": 51.5074, "lng": -0.1278}],
    },
    {
        "wikidata_id": "Q47703", "title": "Inception",
        "tmdb_id": 27205, "media_type": "movie", "year": 2010,
        "poster_path": None, "vote_average": 8.8, "vote_count": 35000,
        "location_count": 1, "countries": ["France"],
        "_title_lower": "inception", "_countries_lower": ["france"],
        "primary_location": {"name": "Paris", "lat": 48.8566, "lng": 2.3522,
                             "country": "France", "wikidata_id": "Q90"},
        "locations": [{"wikidata_id": "Q90", "name": "Paris",
                       "country": "France", "lat": 48.8566, "lng": 2.3522}],
    },
    {
        "wikidata_id": "Q836821", "title": "The Avengers",
        "tmdb_id": 24428, "media_type": "movie", "year": 2012,
        "poster_path": None, "vote_average": 8.0, "vote_count": 28000,
        "location_count": 1, "countries": ["Etats-Unis"],
        "_title_lower": "the avengers", "_countries_lower": ["etats-unis"],
        "primary_location": {"name": "New York", "lat": 40.7128, "lng": -74.006,
                             "country": "Etats-Unis", "wikidata_id": "Q60"},
        "locations": [{"wikidata_id": "Q60", "name": "New York",
                       "country": "Etats-Unis", "lat": 40.7128, "lng": -74.006}],
    },
]


# ---------------------------------------------------------------------------
# Filtres RAM
# ---------------------------------------------------------------------------
def _apply_filters(
    source: list[dict],
    country: str = "",
    q: str = "",
    media_type: str = "",
) -> list[dict]:
    result = source
    if country:
        cl = country.lower()
        result = [f for f in result if any(cl in c for c in f.get("_countries_lower", []))]
    if q:
        ql = q.lower()
        result = [f for f in result if ql in f.get("_title_lower", "")]
    if media_type:
        result = [f for f in result if f.get("media_type") == media_type]
    return result


def _sort_films(source: list[dict], sort: str) -> list[dict]:
    if sort == "count_locations":
        return sorted(source, key=lambda f: f.get("location_count", 0), reverse=True)
    if sort == "rating":
        return sorted(source, key=lambda f: f.get("vote_average") or 0, reverse=True)
    if sort == "year":
        return sorted(source, key=lambda f: f.get("year") or 0, reverse=True)
    if sort == "title":
        return sorted(source, key=lambda f: f.get("_title_lower", ""))
    return source


def _strip_internal(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------
async def get_filming_catalogue(
    page: int = 1,
    per_page: int = 24,
    country: str = "",
    city: str = "",
    media_type: str = "",
    q: str = "",
    sort: str = "count_locations",
    lang: str = "fr",
) -> dict:
    await ensure_catalogue_loaded()

    source      = _catalogue if _catalogue else _FALLBACK
    is_fallback = not bool(_catalogue)

    filtered   = _apply_filters(source, country=country, q=q, media_type=media_type)
    sorted_    = _sort_films(filtered, sort)

    total      = len(sorted_)
    offset     = (page - 1) * per_page
    page_items = sorted_[offset : offset + per_page]

    return {
        "status":      "success",
        "page":        page,
        "per_page":    per_page,
        "total":       total,
        "total_pages": max(1, -(-total // per_page)),
        "results":     [_strip_internal(f) for f in page_items],
        "_loading":    _catalogue_loading,
        "_fallback":   is_fallback,
    }


async def get_filming_stats() -> dict:
    await ensure_catalogue_loaded()
    source = _catalogue if _catalogue else _FALLBACK
    countries: set[str] = set()
    locations: set[str] = set()
    for f in source:
        for c in f.get("countries", []):
            countries.add(c)
        for loc in f.get("locations", []):
            wid = loc.get("wikidata_id", "")
            if wid:
                locations.add(wid)
    return {
        "total_films":     len(source),
        "total_locations": len(locations),
        "total_countries": len(countries),
        "_loading":        _catalogue_loading,
    }


async def get_filming_countries() -> dict:
    await ensure_catalogue_loaded()
    source = _catalogue if _catalogue else _FALLBACK
    counts: dict[str, int] = {}
    for f in source:
        for c in f.get("countries", []):
            if c:
                counts[c] = counts.get(c, 0) + 1
    countries = sorted(
        [{"country": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    return {"countries": countries, "_loading": _catalogue_loading}


async def get_film_locations(tmdb_id: int, media_type: str = "movie") -> dict:
    """Cherche les lieux en RAM (plus de requête Wikidata directe)."""
    await ensure_catalogue_loaded()
    for f in _catalogue:
        if f.get("tmdb_id") == tmdb_id and f.get("media_type") == media_type:
            return {"status": "success", "locations": f.get("locations", [])}
    return {"status": "not_found", "locations": []}