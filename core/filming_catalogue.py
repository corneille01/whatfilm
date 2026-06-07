"""
core/filming_catalogue.py  —  Catalogue lieux de tournage (Wikidata) v3

Architecture "load-once, serve-from-RAM" :
  - Au demarrage, le catalogue complet est charge en arriere-plan par pages SPARQL
  - Les filtres (pays, titre, media_type) sont appliques en Python sur la RAM
  - Wikidata n'est JAMAIS interroge pendant une requete utilisateur
  - Refresh automatique toutes les 24h
  - Fallback statique si Wikidata inaccessible au demarrage
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WIKIDATA_SPARQL   = "https://query.wikidata.org/sparql"
TMDB_BASE         = "https://api.themoviedb.org/3"
TMDB_KEY          = os.getenv("TMDB_API_KEY", "")

CATALOGUE_REFRESH = 3600 * 24   # rafraichit toutes les 24h
SPARQL_PAGE_SIZE  = 500         # lignes par page SPARQL
SPARQL_DELAY      = 3.0         # secondes de politesse entre pages
SPARQL_TIMEOUT    = 60          # timeout par requete SPARQL
SPARQL_MAX_PAGES  = 20          # 20 x 500 = 10 000 films max

# ---------------------------------------------------------------------------
# Etat global en RAM
# ---------------------------------------------------------------------------
_catalogue: list[dict] = []
_catalogue_loaded_at: float = 0.0
_catalogue_loading: bool = False
_catalogue_lock: Optional[asyncio.Lock] = None   # cree a la premiere utilisation


def _get_lock() -> asyncio.Lock:
    global _catalogue_lock
    if _catalogue_lock is None:
        _catalogue_lock = asyncio.Lock()
    return _catalogue_lock


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _wd_id(uri: str) -> str:
    return uri.split("/")[-1] if uri else ""


# ---------------------------------------------------------------------------
# SPARQL — utilise uniquement en tache de fond
# ---------------------------------------------------------------------------
_SPARQL_PAGE = """
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
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en" . }}
}}
GROUP BY ?film ?filmLabel ?tmdb_id ?tmdb_tv_id ?loc ?locLabel ?countryLabel ?year
ORDER BY DESC(?year)
LIMIT {limit}
OFFSET {offset}
"""


async def _sparql_one_page(offset: int, retries: int = 3) -> list[dict]:
    query = _SPARQL_PAGE.format(limit=SPARQL_PAGE_SIZE, offset=offset)
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ShadowFrame/3.0 (https://quelfilm.app) httpx-bg",
    }
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=SPARQL_TIMEOUT) as client:
                r = await client.get(
                    WIKIDATA_SPARQL,
                    params={"query": query, "format": "json"},
                    headers=headers,
                )
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 60)) + 10 * attempt
                    logger.warning("SPARQL bg 429 — attente %ss (offset=%s)", wait, offset)
                    await asyncio.sleep(wait)
                    continue
                if r.status_code == 503:
                    await asyncio.sleep(20 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json().get("results", {}).get("bindings", [])
        except httpx.TimeoutException:
            logger.warning("SPARQL bg timeout offset=%s tentative %s", offset, attempt + 1)
            if attempt < retries - 1:
                await asyncio.sleep(15 * (attempt + 1))
        except Exception as exc:
            logger.warning("SPARQL bg erreur offset=%s: %s", offset, exc)
            if attempt < retries - 1:
                await asyncio.sleep(10 * (attempt + 1))
    return []


def _bindings_to_films(bindings: list[dict]) -> dict[str, FilmWithLocations]:
    films: dict[str, FilmWithLocations] = {}
    for row in bindings:
        fid = _wd_id(row.get("film", {}).get("value", ""))
        if not fid:
            continue

        label   = row.get("filmLabel",  {}).get("value", "")
        tid_raw = row.get("tmdb_id",    {}).get("value", "")
        tv_raw  = row.get("tmdb_tv_id", {}).get("value", "")
        yr_raw  = row.get("year",       {}).get("value", "")

        tmdb_id = int(tid_raw) if tid_raw and tid_raw.isdigit() else None
        mtype   = "movie"
        if tv_raw and tv_raw.isdigit():
            tmdb_id = int(tv_raw)
            mtype   = "tv"

        if fid not in films:
            films[fid] = FilmWithLocations(
                wikidata_id=fid,
                title=label or fid,
                tmdb_id=tmdb_id,
                media_type=mtype,
                year=int(yr_raw) if yr_raw and yr_raw.isdigit() else None,
            )

        lid   = _wd_id(row.get("loc",          {}).get("value", ""))
        lname = row.get("locLabel",             {}).get("value", lid)
        cname = row.get("countryLabel",         {}).get("value", "")
        coord = row.get("coord",                {}).get("value", "")
        lat, lng = _parse_coord(coord)

        existing = {loc.wikidata_id for loc in films[fid].locations}
        if lid and lid not in existing:
            films[fid].locations.append(
                FilmingLocation(wikidata_id=lid, name=lname, country=cname, lat=lat, lng=lng)
            )
    return films


# ---------------------------------------------------------------------------
# Chargement en arriere-plan
# ---------------------------------------------------------------------------
async def _load_catalogue_bg() -> None:
    global _catalogue, _catalogue_loaded_at, _catalogue_loading

    lock = _get_lock()
    async with lock:
        if _catalogue_loading:
            return
        _catalogue_loading = True

    logger.info("Catalogue bg: demarrage chargement Wikidata...")
    all_films: dict[str, FilmWithLocations] = {}
    offset = 0

    for page_num in range(SPARQL_MAX_PAGES):
        bindings = await _sparql_one_page(offset)
        if not bindings:
            logger.info("Catalogue bg: fin a offset=%s (page vide)", offset)
            break

        page_films = _bindings_to_films(bindings)
        for fid, film in page_films.items():
            if fid in all_films:
                existing_lids = {l.wikidata_id for l in all_films[fid].locations}
                for loc in film.locations:
                    if loc.wikidata_id not in existing_lids:
                        all_films[fid].locations.append(loc)
            else:
                all_films[fid] = film

        logger.info(
            "Catalogue bg: page %s — +%s films, total=%s",
            page_num + 1, len(page_films), len(all_films),
        )
        offset += SPARQL_PAGE_SIZE

        if len(bindings) < SPARQL_PAGE_SIZE:
            break   # derniere page, plus besoin d'aller plus loin

        await asyncio.sleep(SPARQL_DELAY)

    films_list = list(all_films.values())

    # Enrichissement TMDB (batch silencieux)
    if TMDB_KEY:
        await _enrich_tmdb_batch(films_list, lang="fr")

    new_catalogue = [_film_to_dict(f) for f in films_list]

    async with lock:
        _catalogue           = new_catalogue
        _catalogue_loaded_at = time.time()
        _catalogue_loading   = False

    logger.info("Catalogue bg: termine — %s films en RAM", len(_catalogue))


async def ensure_catalogue_loaded() -> None:
    now = time.time()
    if _catalogue and (now - _catalogue_loaded_at) < CATALOGUE_REFRESH:
        return
    if _catalogue_loading:
        return
    asyncio.create_task(_load_catalogue_bg())


# ---------------------------------------------------------------------------
# Enrichissement TMDB (tourne en bg pendant le chargement)
# ---------------------------------------------------------------------------
async def _enrich_tmdb_batch(films: list[FilmWithLocations], lang: str = "fr") -> None:
    if not TMDB_KEY:
        return

    async def fetch_one(film: FilmWithLocations) -> None:
        if not film.tmdb_id:
            return
        ep = f"/tv/{film.tmdb_id}" if film.media_type == "tv" else f"/movie/{film.tmdb_id}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"{TMDB_BASE}{ep}",
                    params={"api_key": TMDB_KEY, "language": lang},
                )
                if r.status_code == 200:
                    d = r.json()
                    film.poster_path  = d.get("poster_path")
                    film.vote_average = d.get("vote_average")
                    film.vote_count   = d.get("vote_count")
                    film.overview     = d.get("overview", "")
                    title = d.get("title") or d.get("name")
                    if title:
                        film.title = title
        except Exception as exc:
            logger.debug("TMDB enrich %s: %s", film.tmdb_id, exc)

    for i in range(0, len(films), 10):
        await asyncio.gather(*[fetch_one(f) for f in films[i : i + 10]])
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def _film_to_dict(f: FilmWithLocations) -> dict:
    gps  = [loc for loc in f.locations if loc.lat is not None]
    best = gps[0] if gps else (f.locations[0] if f.locations else None)
    countries_set = {loc.country for loc in f.locations if loc.country}
    return {
        "wikidata_id":      f.wikidata_id,
        "title":            f.title,
        "tmdb_id":          f.tmdb_id,
        "media_type":       f.media_type,
        "year":             f.year,
        "poster_path":      f.poster_path,
        "vote_average":     f.vote_average,
        "vote_count":       f.vote_count,
        "location_count":   len(f.locations),
        "countries":        sorted(countries_set),
        # Cles internes pour filtrage rapide (non envoyees au client)
        "_title_lower":     f.title.lower(),
        "_countries_lower": [c.lower() for c in countries_set],
        "primary_location": {
            "name":        best.name,
            "lat":         best.lat,
            "lng":         best.lng,
            "country":     best.country,
            "wikidata_id": best.wikidata_id,
        } if best else None,
        "locations": [asdict(loc) for loc in f.locations],
    }


def _strip_internal(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Fallback statique (Wikidata indisponible au boot)
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
    await ensure_catalogue_loaded()

    # Chercher d'abord en RAM
    for f in _catalogue:
        if f.get("tmdb_id") == tmdb_id and f.get("media_type") == media_type:
            return {"status": "success", "locations": f.get("locations", [])}

    # Fallback : requete directe Wikidata (film pas encore dans le catalogue)
    tmdb_prop = "P8306" if media_type == "tv" else "P4947"
    query = (
        "SELECT DISTINCT ?loc ?locLabel ?countryLabel ?coord WHERE {"
        f'  ?film wdt:{tmdb_prop} "{tmdb_id}" ; wdt:P915 ?loc . '
        "  OPTIONAL { ?loc wdt:P625 ?coord . } "
        "  OPTIONAL { ?loc wdt:P17 ?country . } "
        '  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en" . } '
        "} LIMIT 30"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={
                    "Accept": "application/sparql-results+json",
                    "User-Agent": "ShadowFrame/3.0 (https://quelfilm.app) httpx",
                },
            )
            r.raise_for_status()
            bindings = r.json().get("results", {}).get("bindings", [])

        locations = []
        seen: set[str] = set()
        for b in bindings:
            lid = _wd_id(b.get("loc", {}).get("value", ""))
            if lid and lid not in seen:
                seen.add(lid)
                lat, lng = _parse_coord(b.get("coord", {}).get("value", ""))
                locations.append({
                    "wikidata_id": lid,
                    "name":    b.get("locLabel",     {}).get("value", lid),
                    "country": b.get("countryLabel", {}).get("value", ""),
                    "lat": lat,
                    "lng": lng,
                })
        return {"status": "success", "locations": locations}
    except Exception as exc:
        logger.error("get_film_locations KO %s: %s", tmdb_id, exc)
        return {"status": "error", "locations": [], "message": str(exc)}