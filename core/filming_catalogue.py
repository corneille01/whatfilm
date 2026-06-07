"""
core/filming_catalogue.py — Catalogue des films avec lieux de tournage disponibles sur Wikidata.

Pipeline :
  1. Wikidata SPARQL → liste des films ayant P915 (filming location) avec coordonnées
  2. Enrichissement TMDB (poster, note, synopsis)
  3. Cache Redis/mémoire + pagination

Pourquoi cette approche ?
  - On ne liste QUE les films qui ont réellement des lieux renseignés sur Wikidata
  - Les coordonnées GPS sont récupérées directement (P625 sur le lieu)
  - L'enrichissement TMDB est fait en batch pour la perf
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
TMDB_BASE       = "https://api.themoviedb.org/3"
TMDB_KEY        = os.getenv("TMDB_API_KEY", "")

# Cache mémoire (clé → (timestamp, data))
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 3600 * 6  # 6 h

# ── Structures ────────────────────────────────────────────────────────────────
@dataclass
class FilmingLocation:
    wikidata_id: str
    name: str
    country: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None

@dataclass
class FilmWithLocations:
    wikidata_id: str
    title: str
    tmdb_id: Optional[int]
    media_type: str           # "movie" | "tv"
    year: Optional[int]
    locations: list[FilmingLocation] = field(default_factory=list)
    # Enrichissement TMDB
    poster_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    overview: Optional[str] = None
    # Calculé
    location_count: int = 0
    countries: list[str] = field(default_factory=list)
    primary_location: Optional[dict] = None   # {name, lat, lng, country}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["location_count"] = len(self.locations)
        d["countries"] = list({loc.country for loc in self.locations if loc.country})
        if self.locations:
            # Priorité aux lieux avec GPS
            gps = [l for l in self.locations if l.lat is not None]
            best = gps[0] if gps else self.locations[0]
            d["primary_location"] = {
                "name": best.name,
                "lat": best.lat,
                "lng": best.lng,
                "country": best.country,
                "wikidata_id": best.wikidata_id,
            }
        d["locations"] = [asdict(l) for l in self.locations]
        return d


# ── Cache helpers ─────────────────────────────────────────────────────────────
def _cache_key(*args) -> str:
    return hashlib.md5("|".join(str(a) for a in args).encode()).hexdigest()

def _cache_get(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None

def _cache_set(key: str, data):
    _CACHE[key] = (time.time(), data)


# ── Requête SPARQL Wikidata ───────────────────────────────────────────────────
SPARQL_QUERY = """
SELECT DISTINCT
  ?film ?filmLabel
  ?tmdb_id ?tmdb_tv_id
  ?loc ?locLabel
  ?country ?countryLabel
  (SAMPLE(?coord) AS ?coord)
  ?year
WHERE {{
  # Films ou séries TV avec lieu de tournage (P915)
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .

  # Filtre par pays (optionnel)
  {country_filter}

  # Filtre par titre (optionnel)
  {title_filter}

  # Coordonnées du lieu
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}

  # ID TMDB
  OPTIONAL {{ ?film wdt:P4947 ?tmdb_id . }}
  OPTIONAL {{ ?film wdt:P8306 ?tmdb_tv_id . }}

  # Année de publication
  OPTIONAL {{
    ?film wdt:P577 ?date .
    BIND(YEAR(?date) AS ?year)
  }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en" . }}
}}
GROUP BY ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?country ?countryLabel ?year
ORDER BY DESC(?year)
LIMIT {limit}
OFFSET {offset}
"""

SPARQL_COUNT_QUERY = """
SELECT (COUNT(DISTINCT ?film) AS ?count) WHERE {{
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  {country_filter}
  {title_filter}
}}
"""

SPARQL_STATS_QUERY = """
SELECT
  (COUNT(DISTINCT ?film) AS ?total_films)
  (COUNT(DISTINCT ?loc) AS ?total_locations)
  (COUNT(DISTINCT ?country) AS ?total_countries)
WHERE {
  VALUES ?type { wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  OPTIONAL { ?loc wdt:P17 ?country . }
}
"""

SPARQL_COUNTRIES_QUERY = """
SELECT ?countryLabel (COUNT(DISTINCT ?film) AS ?count)
WHERE {
  VALUES ?type { wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  ?loc wdt:P17 ?country .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en" . }
}
GROUP BY ?countryLabel
ORDER BY DESC(?count)
LIMIT 80
"""


async def _sparql(query: str, timeout: int = 30) -> dict:
    """Exécute une requête SPARQL sur Wikidata."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ShadowFrame/1.0 (https://shadowframe.io ; contact@shadowframe.io)",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()


def _parse_coord(coord_str: str) -> tuple[Optional[float], Optional[float]]:
    """Parse 'Point(lng lat)' → (lat, lng)."""
    if not coord_str:
        return None, None
    try:
        # Format WKT Wikidata : Point(longitude latitude)
        inner = coord_str.replace("Point(", "").replace(")", "").strip()
        parts = inner.split()
        if len(parts) == 2:
            lng, lat = float(parts[0]), float(parts[1])
            # Sanity check
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    except Exception:
        pass
    return None, None


def _extract_wikidata_id(uri: str) -> str:
    return uri.split("/")[-1] if uri else ""


def _build_films_from_sparql(bindings: list[dict]) -> dict[str, FilmWithLocations]:
    """Agrège les lignes SPARQL (une par loc) en dict wikidata_id → FilmWithLocations."""
    films: dict[str, FilmWithLocations] = {}

    for row in bindings:
        film_uri   = row.get("film", {}).get("value", "")
        film_wd_id = _extract_wikidata_id(film_uri)
        if not film_wd_id:
            continue

        film_label  = row.get("filmLabel", {}).get("value", "")
        tmdb_id_raw = row.get("tmdb_id", {}).get("value", "")
        tmdb_tv_raw = row.get("tmdb_tv_id", {}).get("value", "")
        year_raw    = row.get("year", {}).get("value", "")

        # Déterminer media_type et tmdb_id
        tmdb_id    = int(tmdb_id_raw) if tmdb_id_raw and tmdb_id_raw.isdigit() else None
        media_type = "movie"
        if tmdb_tv_raw and tmdb_tv_raw.isdigit():
            tmdb_id    = int(tmdb_tv_raw)
            media_type = "tv"

        year = int(year_raw) if year_raw and year_raw.isdigit() else None

        if film_wd_id not in films:
            films[film_wd_id] = FilmWithLocations(
                wikidata_id = film_wd_id,
                title       = film_label or film_wd_id,
                tmdb_id     = tmdb_id,
                media_type  = media_type,
                year        = year,
            )

        # Lieu de tournage
        loc_uri   = row.get("loc", {}).get("value", "")
        loc_label = row.get("locLabel", {}).get("value", "")
        coord_raw = row.get("coord", {}).get("value", "")
        country   = row.get("countryLabel", {}).get("value", "")
        loc_wd_id = _extract_wikidata_id(loc_uri)

        # Éviter les doublons de lieu
        existing_ids = {l.wikidata_id for l in films[film_wd_id].locations}
        if loc_wd_id and loc_wd_id not in existing_ids:
            lat, lng = _parse_coord(coord_raw)
            films[film_wd_id].locations.append(FilmingLocation(
                wikidata_id = loc_wd_id,
                name        = loc_label or loc_wd_id,
                country     = country,
                lat         = lat,
                lng         = lng,
            ))

    return films


# ── Enrichissement TMDB ───────────────────────────────────────────────────────
async def _enrich_tmdb_batch(
    films: list[FilmWithLocations],
    lang: str = "fr",
) -> None:
    """Enrichit en parallèle (poster, note, overview) via TMDB."""
    if not TMDB_KEY:
        return

    async def fetch_one(film: FilmWithLocations):
        if not film.tmdb_id:
            return
        endpoint = f"/tv/{film.tmdb_id}" if film.media_type == "tv" else f"/movie/{film.tmdb_id}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"{TMDB_BASE}{endpoint}",
                    params={"api_key": TMDB_KEY, "language": lang},
                )
                if r.status_code == 200:
                    d = r.json()
                    film.poster_path   = d.get("poster_path")
                    film.vote_average  = d.get("vote_average")
                    film.vote_count    = d.get("vote_count")
                    film.overview      = d.get("overview", "")
                    # Mise à jour du titre avec la bonne langue
                    local_title = d.get("title") or d.get("name")
                    if local_title:
                        film.title = local_title
        except Exception as e:
            logger.debug(f"TMDB enrich KO for {film.tmdb_id}: {e}")

    # Batches de 10 pour ne pas surcharger l'API
    batch_size = 10
    for i in range(0, len(films), batch_size):
        batch = films[i:i + batch_size]
        await asyncio.gather(*[fetch_one(f) for f in batch])
        if i + batch_size < len(films):
            await asyncio.sleep(0.1)


# ── API publique ──────────────────────────────────────────────────────────────
async def get_filming_catalogue(
    page: int = 1,
    per_page: int = 24,
    country: str = "",
    city: str = "",
    media_type: str = "",
    q: str = "",
    sort: str = "count_locations",   # count_locations | rating | year | title
    lang: str = "fr",
) -> dict:
    """
    Retourne le catalogue paginé des films avec lieux de tournage.

    Returns:
        {
            status: "success",
            page, total_pages, total,
            results: [FilmWithLocations.to_dict(), ...]
        }
    """
    cache_key = _cache_key("catalogue", page, per_page, country, city, media_type, q, sort, lang)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # ── Construire les filtres SPARQL ────────────────────────────────────────
    country_filter = ""
    if country:
        # On filtre sur le label du pays
        country_filter = f'?country rdfs:label "{country}"@fr .'

    title_filter = ""
    if q:
        safe_q = q.replace('"', '\\"')
        title_filter = f'FILTER(CONTAINS(LCASE(?filmLabel), LCASE("{safe_q}")))'

    # Media type filter : on ne peut pas filtrer précisément par tmdb_id présent
    # on filtrera en Python après
    media_filter_post = media_type  # "movie" | "tv" | ""

    offset   = (page - 1) * per_page
    # On récupère plus pour pouvoir trier/filtrer côté Python si besoin
    sparql_limit = per_page * 3

    query = SPARQL_QUERY.format(
        country_filter = country_filter,
        title_filter   = title_filter,
        lang           = {"fr": "fr", "en": "en", "es": "es", "de": "de", "zh": "zh"}.get(lang, "fr"),
        limit          = sparql_limit,
        offset         = offset,
    )

    try:
        raw = await _sparql(query)
    except Exception as e:
        logger.error(f"Wikidata SPARQL KO: {e}")
        return {"status": "error", "message": str(e)}

    bindings = raw.get("results", {}).get("bindings", [])
    films_dict = _build_films_from_sparql(bindings)
    films_list = list(films_dict.values())

    # ── Filtre media_type post-SPARQL ────────────────────────────────────────
    if media_filter_post:
        films_list = [f for f in films_list if f.media_type == media_filter_post]

    # ── Tri ──────────────────────────────────────────────────────────────────
    if sort == "count_locations":
        films_list.sort(key=lambda f: len(f.locations), reverse=True)
    elif sort == "rating":
        films_list.sort(key=lambda f: f.vote_average or 0, reverse=True)
    elif sort == "year":
        films_list.sort(key=lambda f: f.year or 0, reverse=True)
    elif sort == "title":
        films_list.sort(key=lambda f: f.title.lower())

    total = len(films_list)

    # ── Pagination ───────────────────────────────────────────────────────────
    start = 0  # déjà paginé via OFFSET dans SPARQL, mais on re-pagine localement
    page_films = films_list[:per_page]

    # ── Enrichissement TMDB ──────────────────────────────────────────────────
    await _enrich_tmdb_batch(page_films, lang=lang)

    # ── Préparer réponse ─────────────────────────────────────────────────────
    results = []
    for f in page_films:
        d = f.to_dict()
        # Calculer countries et primary_location
        d["location_count"] = len(f.locations)
        d["countries"] = list({loc.country for loc in f.locations if loc.country})
        gps = [l for l in f.locations if l.lat is not None]
        best = gps[0] if gps else (f.locations[0] if f.locations else None)
        d["primary_location"] = {
            "name": best.name,
            "lat": best.lat,
            "lng": best.lng,
            "country": best.country,
            "wikidata_id": best.wikidata_id,
        } if best else None
        results.append(d)

    # Estimer le total (Wikidata ne donne pas de COUNT efficacement avec GROUP BY)
    # On utilise le nombre réel de cette page × un facteur pour l'UX
    estimated_total = total if total < sparql_limit else total + offset

    response = {
        "status":      "success",
        "page":        page,
        "per_page":    per_page,
        "total":       estimated_total,
        "total_pages": max(1, -(-estimated_total // per_page)),  # ceil division
        "results":     results,
    }
    _cache_set(cache_key, response)
    return response


async def get_filming_stats() -> dict:
    """Stats globales : nombre de films, lieux, pays."""
    cache_key = "filming_stats"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        raw = await _sparql(SPARQL_STATS_QUERY, timeout=20)
        bindings = raw.get("results", {}).get("bindings", [])
        if bindings:
            b = bindings[0]
            result = {
                "total_films":     int(b.get("total_films",     {}).get("value", 0)),
                "total_locations": int(b.get("total_locations", {}).get("value", 0)),
                "total_countries": int(b.get("total_countries", {}).get("value", 0)),
            }
        else:
            result = {"total_films": 0, "total_locations": 0, "total_countries": 0}
    except Exception as e:
        logger.error(f"Filming stats KO: {e}")
        result = {"total_films": 0, "total_locations": 0, "total_countries": 0}

    _cache_set(cache_key, result)
    return result


async def get_filming_countries() -> dict:
    """Liste des pays avec le nombre de films tournés là-bas."""
    cache_key = "filming_countries"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        raw = await _sparql(SPARQL_COUNTRIES_QUERY, timeout=20)
        bindings = raw.get("results", {}).get("bindings", [])
        countries = [
            {
                "country": b.get("countryLabel", {}).get("value", ""),
                "count":   int(b.get("count", {}).get("value", 0)),
            }
            for b in bindings
            if b.get("countryLabel", {}).get("value")
        ]
    except Exception as e:
        logger.error(f"Filming countries KO: {e}")
        countries = []

    result = {"countries": countries}
    _cache_set(cache_key, result)
    return result


async def get_film_locations(tmdb_id: int, media_type: str = "movie") -> dict:
    """
    Lieux de tournage d'un film spécifique via son TMDB ID.
    Utilisé par /movie/{id}/locations dans l'existant.
    """
    cache_key = _cache_key("film_loc", tmdb_id, media_type)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # Prop TMDB sur Wikidata
    tmdb_prop = "P8306" if media_type == "tv" else "P4947"

    query = f"""
SELECT DISTINCT ?loc ?locLabel ?country ?countryLabel ?coord WHERE {{
  ?film wdt:{tmdb_prop} "{tmdb_id}" ;
        wdt:P915 ?loc .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
}}
LIMIT 50
"""
    try:
        raw = await _sparql(query, timeout=15)
        bindings = raw.get("results", {}).get("bindings", [])
        locations = []
        seen = set()
        for b in bindings:
            loc_id  = _extract_wikidata_id(b.get("loc", {}).get("value", ""))
            name    = b.get("locLabel", {}).get("value", loc_id)
            country = b.get("countryLabel", {}).get("value", "")
            coord   = b.get("coord", {}).get("value", "")
            lat, lng = _parse_coord(coord)
            if loc_id and loc_id not in seen:
                seen.add(loc_id)
                locations.append({
                    "wikidata_id": loc_id,
                    "name":        name,
                    "country":     country,
                    "lat":         lat,
                    "lng":         lng,
                })
        result = {"status": "success", "locations": locations}
    except Exception as e:
        logger.error(f"Film locations KO for {tmdb_id}: {e}")
        result = {"status": "error", "locations": [], "message": str(e)}

    _cache_set(cache_key, result)
    return result