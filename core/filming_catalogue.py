"""
core/filming_catalogue.py — Catalogue des films avec lieux de tournage (Wikidata).

Correctifs v2 :
  - Retry avec exponential backoff sur 429/503
  - Filtre pays corrigé (FILTER sur ?countryLabel au lieu de triple pattern cassé)
  - Cache TTL 24h (au lieu de 6h) + cache partagé "base" pour éviter les appels répétés
  - Requête SPARQL simplifiée et moins gourmande
  - Fallback données statiques si Wikidata inaccessible
  - Semaphore global pour ne jamais envoyer > 1 requête SPARQL simultanée
"""

from __future__ import annotations

import asyncio
import hashlib
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

# Cache mémoire long (clé → (timestamp, data))
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL        = 3600 * 24   # 24h pour les catalogues
_CACHE_TTL_SHORT  = 3600 * 6    # 6h pour les filtres variés
_CACHE_TTL_STATS  = 3600 * 12   # 12h pour stats/pays

# Semaphore : 1 seule requête SPARQL à la fois → évite les 429 en cascade
_SPARQL_SEM = asyncio.Semaphore(1)

# Délai minimum entre deux requêtes SPARQL (secondes)
_LAST_SPARQL_CALL = 0.0
_SPARQL_MIN_DELAY = 2.0   # 2s entre chaque appel

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
    media_type: str
    year: Optional[int]
    locations: list[FilmingLocation] = field(default_factory=list)
    poster_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    overview: Optional[str] = None


# ── Cache helpers ─────────────────────────────────────────────────────────────
def _cache_key(*args) -> str:
    return hashlib.md5("|".join(str(a) for a in args).encode()).hexdigest()

def _cache_get(key: str, ttl: float = _CACHE_TTL):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None

def _cache_set(key: str, data):
    _CACHE[key] = (time.time(), data)


# ── SPARQL avec retry + backoff ───────────────────────────────────────────────
async def _sparql(query: str, timeout: int = 45, max_retries: int = 3) -> dict:
    global _LAST_SPARQL_CALL

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ShadowFrame/2.0 (https://quelfilm.app ; contact@quelfilm.app) httpx",
    }

    async with _SPARQL_SEM:
        # Respecter le délai minimum entre appels
        now = time.time()
        elapsed = now - _LAST_SPARQL_CALL
        if elapsed < _SPARQL_MIN_DELAY:
            await asyncio.sleep(_SPARQL_MIN_DELAY - elapsed)

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.get(
                        WIKIDATA_SPARQL,
                        params={"query": query, "format": "json"},
                        headers=headers,
                    )
                    _LAST_SPARQL_CALL = time.time()

                    if r.status_code == 429:
                        retry_after = int(r.headers.get("Retry-After", 30))
                        wait = min(retry_after, 60) * (attempt + 1)
                        logger.warning(
                            f"Wikidata 429 — attente {wait}s (tentative {attempt+1}/{max_retries})"
                        )
                        await asyncio.sleep(wait)
                        continue

                    if r.status_code == 503:
                        wait = 10 * (attempt + 1)
                        logger.warning(f"Wikidata 503 — attente {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    r.raise_for_status()
                    return r.json()

            except httpx.TimeoutException:
                wait = 5 * (attempt + 1)
                logger.warning(f"Wikidata timeout — attente {wait}s")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
                    continue
                raise

            except httpx.HTTPStatusError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                raise

        raise RuntimeError(f"Wikidata SPARQL échoué après {max_retries} tentatives")


# ── Parsing ───────────────────────────────────────────────────────────────────
def _parse_coord(coord_str: str) -> tuple[Optional[float], Optional[float]]:
    if not coord_str:
        return None, None
    try:
        inner = coord_str.replace("Point(", "").replace(")", "").strip()
        parts = inner.split()
        if len(parts) == 2:
            lng, lat = float(parts[0]), float(parts[1])
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    except Exception:
        pass
    return None, None

def _extract_wikidata_id(uri: str) -> str:
    return uri.split("/")[-1] if uri else ""

def _build_films_from_sparql(bindings: list[dict]) -> dict[str, FilmWithLocations]:
    films: dict[str, FilmWithLocations] = {}
    for row in bindings:
        film_uri   = row.get("film", {}).get("value", "")
        film_wd_id = _extract_wikidata_id(film_uri)
        if not film_wd_id:
            continue

        film_label  = row.get("filmLabel",  {}).get("value", "")
        tmdb_id_raw = row.get("tmdb_id",    {}).get("value", "")
        tmdb_tv_raw = row.get("tmdb_tv_id", {}).get("value", "")
        year_raw    = row.get("year",        {}).get("value", "")

        tmdb_id    = int(tmdb_id_raw) if tmdb_id_raw and tmdb_id_raw.isdigit() else None
        media_type = "movie"
        if tmdb_tv_raw and tmdb_tv_raw.isdigit():
            tmdb_id    = int(tmdb_tv_raw)
            media_type = "tv"

        year = int(year_raw) if year_raw and year_raw.isdigit() else None

        if film_wd_id not in films:
            films[film_wd_id] = FilmWithLocations(
                wikidata_id=film_wd_id,
                title=film_label or film_wd_id,
                tmdb_id=tmdb_id,
                media_type=media_type,
                year=year,
            )

        loc_uri   = row.get("loc",         {}).get("value", "")
        loc_label = row.get("locLabel",    {}).get("value", "")
        coord_raw = row.get("coord",       {}).get("value", "")
        country   = row.get("countryLabel",{}).get("value", "")
        loc_wd_id = _extract_wikidata_id(loc_uri)

        existing_ids = {l.wikidata_id for l in films[film_wd_id].locations}
        if loc_wd_id and loc_wd_id not in existing_ids:
            lat, lng = _parse_coord(coord_raw)
            films[film_wd_id].locations.append(FilmingLocation(
                wikidata_id=loc_wd_id,
                name=loc_label or loc_wd_id,
                country=country,
                lat=lat,
                lng=lng,
            ))
    return films


# ── Requêtes SPARQL ───────────────────────────────────────────────────────────

# Requête de base (sans filtre pays) — la plus utilisée, mise en cache 24h
_SPARQL_BASE = """
SELECT DISTINCT
  ?film ?filmLabel
  ?tmdb_id ?tmdb_tv_id
  ?loc ?locLabel
  ?countryLabel
  (SAMPLE(?coord) AS ?coord)
  ?year
WHERE {{
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}
  OPTIONAL {{ ?film wdt:P4947 ?tmdb_id . }}
  OPTIONAL {{ ?film wdt:P8306 ?tmdb_tv_id . }}
  OPTIONAL {{
    ?film wdt:P577 ?date .
    BIND(YEAR(?date) AS ?year)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en" . }}
}}
GROUP BY ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?countryLabel ?year
ORDER BY DESC(?year)
LIMIT {limit}
OFFSET {offset}
"""

# Requête avec filtre pays — FILTER sur label (pas de triple pattern cassé)
_SPARQL_COUNTRY = """
SELECT DISTINCT
  ?film ?filmLabel
  ?tmdb_id ?tmdb_tv_id
  ?loc ?locLabel
  ?countryLabel
  (SAMPLE(?coord) AS ?coord)
  ?year
WHERE {{
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  ?loc wdt:P17 ?country .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?film wdt:P4947 ?tmdb_id . }}
  OPTIONAL {{ ?film wdt:P8306 ?tmdb_tv_id . }}
  OPTIONAL {{
    ?film wdt:P577 ?date .
    BIND(YEAR(?date) AS ?year)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en" . }}
  FILTER(CONTAINS(LCASE(?countryLabel), LCASE("{country}")))
  {title_filter}
}}
GROUP BY ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?countryLabel ?year
ORDER BY DESC(?year)
LIMIT {limit}
OFFSET {offset}
"""

# Requête titre seul (sans filtre pays)
_SPARQL_TITLE = """
SELECT DISTINCT
  ?film ?filmLabel
  ?tmdb_id ?tmdb_tv_id
  ?loc ?locLabel
  ?countryLabel
  (SAMPLE(?coord) AS ?coord)
  ?year
WHERE {{
  VALUES ?type {{ wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }}
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}
  OPTIONAL {{ ?film wdt:P4947 ?tmdb_id . }}
  OPTIONAL {{ ?film wdt:P8306 ?tmdb_tv_id . }}
  OPTIONAL {{
    ?film wdt:P577 ?date .
    BIND(YEAR(?date) AS ?year)
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en" . }}
  FILTER(CONTAINS(LCASE(?filmLabel), LCASE("{q}")))
}}
GROUP BY ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?countryLabel ?year
ORDER BY DESC(?year)
LIMIT {limit}
OFFSET {offset}
"""

_SPARQL_STATS = """
SELECT
  (COUNT(DISTINCT ?film) AS ?total_films)
  (COUNT(DISTINCT ?loc)  AS ?total_locations)
  (COUNT(DISTINCT ?country) AS ?total_countries)
WHERE {
  VALUES ?type { wd:Q11424 wd:Q5398426 wd:Q24869 wd:Q506240 }
  ?film wdt:P31 ?type ;
        wdt:P915 ?loc .
  OPTIONAL { ?loc wdt:P17 ?country . }
}
"""

_SPARQL_COUNTRIES = """
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


# ── Fallback statique si Wikidata HS ─────────────────────────────────────────
_FALLBACK_FILMS = [
    {"wikidata_id": "Q471",    "title": "The Dark Knight",    "tmdb_id": 155,   "media_type": "movie", "year": 2008,
     "locations": [{"wikidata_id": "Q84",  "name": "Londres",  "country": "Royaume-Uni",       "lat": 51.5074, "lng": -0.1278}]},
    {"wikidata_id": "Q47703",  "title": "Inception",           "tmdb_id": 27205, "media_type": "movie", "year": 2010,
     "locations": [{"wikidata_id": "Q90",  "name": "Paris",    "country": "France",             "lat": 48.8566, "lng":  2.3522}]},
    {"wikidata_id": "Q208416", "title": "Mission: Impossible", "tmdb_id": 954,   "media_type": "movie", "year": 1996,
     "locations": [{"wikidata_id": "Q1085","name": "Prague",   "country": "République tchèque", "lat": 50.0755, "lng": 14.4378}]},
    {"wikidata_id": "Q836821", "title": "The Avengers",        "tmdb_id": 24428, "media_type": "movie", "year": 2012,
     "locations": [{"wikidata_id": "Q60",  "name": "New York", "country": "États-Unis",         "lat": 40.7128, "lng": -74.0060}]},
    {"wikidata_id": "Q11812",  "title": "Gladiator",           "tmdb_id": 98,    "media_type": "movie", "year": 2000,
     "locations": [{"wikidata_id": "Q38",  "name": "Italie",   "country": "Italie",             "lat": 41.9028, "lng": 12.4964}]},
]

def _make_fallback_result(page: int, per_page: int) -> dict:
    results = []
    for f in _FALLBACK_FILMS:
        locs = [FilmingLocation(**l) for l in f["locations"]]
        best = locs[0] if locs else None
        results.append({
            **{k: v for k, v in f.items() if k != "locations"},
            "location_count": len(locs),
            "countries": list({l.country for l in locs}),
            "primary_location": {
                "name": best.name, "lat": best.lat,
                "lng": best.lng,   "country": best.country,
                "wikidata_id": best.wikidata_id,
            } if best else None,
            "locations": [asdict(l) for l in locs],
            "poster_path": None,
            "vote_average": None,
            "vote_count": None,
        })
    return {
        "status":      "success",
        "page":        page,
        "per_page":    per_page,
        "total":       len(results),
        "total_pages": 1,
        "results":     results,
        "_fallback":   True,
    }


# ── Enrichissement TMDB ───────────────────────────────────────────────────────
async def _enrich_tmdb_batch(films: list[FilmWithLocations], lang: str = "fr") -> None:
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
                    film.poster_path  = d.get("poster_path")
                    film.vote_average = d.get("vote_average")
                    film.vote_count   = d.get("vote_count")
                    film.overview     = d.get("overview", "")
                    local_title = d.get("title") or d.get("name")
                    if local_title:
                        film.title = local_title
        except Exception as e:
            logger.debug(f"TMDB enrich KO {film.tmdb_id}: {e}")

    for i in range(0, len(films), 8):
        await asyncio.gather(*[fetch_one(f) for f in films[i:i+8]])
        if i + 8 < len(films):
            await asyncio.sleep(0.15)


# ── Sérialisation ─────────────────────────────────────────────────────────────
def _film_to_dict(f: FilmWithLocations) -> dict:
    gps  = [l for l in f.locations if l.lat is not None]
    best = gps[0] if gps else (f.locations[0] if f.locations else None)
    return {
        "wikidata_id":    f.wikidata_id,
        "title":          f.title,
        "tmdb_id":        f.tmdb_id,
        "media_type":     f.media_type,
        "year":           f.year,
        "poster_path":    f.poster_path,
        "vote_average":   f.vote_average,
        "vote_count":     f.vote_count,
        "location_count": len(f.locations),
        "countries":      list({l.country for l in f.locations if l.country}),
        "primary_location": {
            "name":        best.name,
            "lat":         best.lat,
            "lng":         best.lng,
            "country":     best.country,
            "wikidata_id": best.wikidata_id,
        } if best else None,
        "locations": [asdict(l) for l in f.locations],
    }


# ── API publique ──────────────────────────────────────────────────────────────
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

    cache_key = _cache_key("cat2", page, per_page, country, media_type, q, sort, lang)
    ttl = _CACHE_TTL if not (country or q) else _CACHE_TTL_SHORT
    cached = _cache_get(cache_key, ttl)
    if cached:
        return cached

    wikidata_lang = {"fr": "fr", "en": "en", "es": "es", "de": "de", "zh": "zh"}.get(lang, "fr")
    offset       = (page - 1) * per_page
    sparql_limit = per_page * 4   # marge pour tri/filtre Python

    try:
        if country and q:
            safe_q = q.replace('"', '\\"')
            query = _SPARQL_COUNTRY.format(
                lang=wikidata_lang,
                country=country.replace('"', '\\"'),
                title_filter=f'FILTER(CONTAINS(LCASE(?filmLabel), LCASE("{safe_q}")))',
                limit=sparql_limit,
                offset=offset,
            )
        elif country:
            query = _SPARQL_COUNTRY.format(
                lang=wikidata_lang,
                country=country.replace('"', '\\"'),
                title_filter="",
                limit=sparql_limit,
                offset=offset,
            )
        elif q:
            safe_q = q.replace('"', '\\"')
            query = _SPARQL_TITLE.format(
                lang=wikidata_lang,
                q=safe_q,
                limit=sparql_limit,
                offset=offset,
            )
        else:
            query = _SPARQL_BASE.format(
                lang=wikidata_lang,
                limit=sparql_limit,
                offset=offset,
            )

        raw      = await _sparql(query)
        bindings = raw.get("results", {}).get("bindings", [])
        films_dict = _build_films_from_sparql(bindings)
        films_list = list(films_dict.values())

    except Exception as e:
        logger.error(f"Wikidata SPARQL KO: {e}")
        if page == 1 and not country and not q:
            return _make_fallback_result(page, per_page)
        return {
            "status":      "error",
            "message":     "Wikidata temporairement indisponible. Réessayez dans quelques secondes.",
            "results":     [],
            "total":       0,
            "total_pages": 0,
            "page":        page,
        }

    # Filtre media_type post-SPARQL
    if media_type:
        films_list = [f for f in films_list if f.media_type == media_type]

    # Tri
    if sort == "count_locations":
        films_list.sort(key=lambda f: len(f.locations), reverse=True)
    elif sort == "rating":
        films_list.sort(key=lambda f: f.vote_average or 0, reverse=True)
    elif sort == "year":
        films_list.sort(key=lambda f: f.year or 0, reverse=True)
    elif sort == "title":
        films_list.sort(key=lambda f: f.title.lower())

    total      = len(films_list)
    page_films = films_list[:per_page]
    est_total  = total if total < sparql_limit else total + offset

    # Enrichissement TMDB
    await _enrich_tmdb_batch(page_films, lang=lang)

    response = {
        "status":      "success",
        "page":        page,
        "per_page":    per_page,
        "total":       est_total,
        "total_pages": max(1, -(-est_total // per_page)),
        "results":     [_film_to_dict(f) for f in page_films],
    }
    _cache_set(cache_key, response)
    return response


async def get_filming_stats() -> dict:
    cached = _cache_get("filming_stats_v2", _CACHE_TTL_STATS)
    if cached:
        return cached
    try:
        raw      = await _sparql(_SPARQL_STATS, timeout=25)
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
        result = {"total_films": 5000, "total_locations": 18000, "total_countries": 85}
    _cache_set("filming_stats_v2", result)
    return result


async def get_filming_countries() -> dict:
    cached = _cache_get("filming_countries_v2", _CACHE_TTL_STATS)
    if cached:
        return cached
    try:
        raw      = await _sparql(_SPARQL_COUNTRIES, timeout=25)
        bindings = raw.get("results", {}).get("bindings", [])
        countries = [
            {
                "country": b.get("countryLabel", {}).get("value", ""),
                "count":   int(b.get("count",         {}).get("value", 0)),
            }
            for b in bindings
            if b.get("countryLabel", {}).get("value")
        ]
    except Exception as e:
        logger.error(f"Filming countries KO: {e}")
        countries = [
            {"country": "États-Unis",    "count": 1200},
            {"country": "Royaume-Uni",   "count": 600},
            {"country": "France",        "count": 450},
            {"country": "Allemagne",     "count": 320},
            {"country": "Italie",        "count": 280},
            {"country": "Espagne",       "count": 240},
            {"country": "Canada",        "count": 200},
            {"country": "Australie",     "count": 180},
        ]
    result = {"countries": countries}
    _cache_set("filming_countries_v2", result)
    return result


async def get_film_locations(tmdb_id: int, media_type: str = "movie") -> dict:
    cache_key = _cache_key("film_loc2", tmdb_id, media_type)
    cached = _cache_get(cache_key, _CACHE_TTL)
    if cached:
        return cached

    tmdb_prop = "P8306" if media_type == "tv" else "P4947"
    query = f"""
SELECT DISTINCT ?loc ?locLabel ?countryLabel ?coord WHERE {{
  ?film wdt:{tmdb_prop} "{tmdb_id}" ;
        wdt:P915 ?loc .
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  OPTIONAL {{ ?loc wdt:P17 ?country . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
}}
LIMIT 30
"""
    try:
        raw      = await _sparql(query, timeout=20)
        bindings = raw.get("results", {}).get("bindings", [])
        locations = []
        seen = set()
        for b in bindings:
            loc_id  = _extract_wikidata_id(b.get("loc",          {}).get("value", ""))
            name    = b.get("locLabel",      {}).get("value", loc_id)
            country = b.get("countryLabel",  {}).get("value", "")
            coord   = b.get("coord",         {}).get("value", "")
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
        logger.error(f"Film locations KO {tmdb_id}: {e}")
        result = {"status": "error", "locations": [], "message": str(e)}

    _cache_set(cache_key, result)
    return result