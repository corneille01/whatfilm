"""
core/wikidata.py — Recherche et enrichissement de films via Wikidata.

Couche 2 du pipeline de recherche, entre la cascade TMDB (couche 1)
et le web search DDG (couche 3).

────────────────────────────────────────────────────────────────
 FIX v3 (juillet 2026) — LIEUX DE TOURNAGE 100% LOCAUX
────────────────────────────────────────────────────────────────
Les lieux de tournage (get_filming_locations) et l'enrichissement
(get_wikidata_enrichment) NE FONT PLUS AUCUN APPEL RÉSEAU vers
Wikidata (ni SPARQL, ni wbgetentities).

À la place, ils lisent un fichier catalogue_filming.json local
(chargé une seule fois en mémoire au premier accès), au format :

    [
      {
        "wikidata_id": "Q1992646",
        "title": "Le Prix du silence",
        "tmdb_id": 80890,
        "media_type": "movie",
        "year": 1949,
        "locations": [
          {
            "wikidata_id": "Q65",
            "name": "Los Angeles",
            "city": "Non spécifié",
            "country": "Inconnu",
            "lat": 34.05223,
            "lng": -118.24368
          }
        ]
      },
      ...
    ]

Conséquences :
  - Plus de SPARQL 429 / plus d'attente 65s / plus de retry
  - Latence de get_filming_locations() proche de 0ms (lookup dict)
  - L'équipe créative (crew), le cast Wikidata, l'EIDR, le budget
    et le box-office ne sont PLUS résolus (le catalogue local ne
    contient que titre/tmdb_id/locations). get_wikidata_enrichment()
    renvoie donc ces champs vides/None — c'est un choix assumé.
  - Le fichier catalogue_filming.json doit être tenu à jour
    manuellement (ou par un script offline séparé qui, lui, peut
    continuer d'interroger Wikidata en batch hors production).

La recherche d'identification par titre (wikidata_search_candidates,
déclenchée sur titres CJK/coréens via should_trigger_wikidata) reste
INCHANGÉE et continue d'utiliser l'API Wikidata en direct
(wbsearchentities / wbgetentities). Ce n'est pas elle qui générait
les erreurs 429 vues dans les logs — ce sont les fonctions dédiées
aux lieux de tournage. Si tu veux aussi la basculer en local un jour,
il faudra un catalogue indexé par titre (pas seulement par tmdb_id).
────────────────────────────────────────────────────────────────

Nouvelles propriétés extraites (v2, encore utilisées par la recherche
par titre) :
  P57   = réalisateur
  P58   = scénariste
  P161  = acteur (avec qualifier P453 = nom du personnage)
  P162  = producteur
  P272  = société de production
  P344  = directeur de la photographie
  P364  = langue originale
  P495  = pays d'origine
  P750  = distributeur
  P840  = lieu narratif (où se déroule l'histoire)
  P86   = compositeur de la musique
  P1040 = monteur
  P2047 = durée (en minutes)
  P2704 = identifiant EIDR (standard industrie audiovisuelle)
  P915  = lieu de tournage (avec coordonnées GPS via P625)
  P625  = coordonnées géographiques (récupérées sur les entités de lieu)

Architecture :
  1. wikidata_search(titre, lang)       → liste de QIDs + labels           [LIVE]
  2. wikidata_to_tmdb_candidates()      → pipeline complet → candidats     [LIVE]
  3. get_filming_locations(tmdb_id)     → [{name, lat, lng, ...}]          [LOCAL]
  4. get_wikidata_enrichment(tmdb_id)   → dict lieux (+ crew vide)         [LOCAL]
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import httpx

# ════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════

_WD_API     = "https://www.wikidata.org/w/api.php"
_USER_AGENT = "ShadowFrame/2.0 (film identification + enrichment; https://quelfilm.app)"

# ── Identifiants externes ─────────────────────────────────────
_P_TMDB_MOVIE  = "P4947"
_P_TMDB_TV     = "P4983"
_P_IMDB        = "P345"
_P_EIDR        = "P2704"   # EIDR — standard industrie (UGC compliance, B2B)

# ── Métadonnées principales ───────────────────────────────────
_P_INSTANCE_OF = "P31"
_P_PUB_DATE    = "P577"
_P_ORIG_LANG   = "P364"    # langue originale du film/série
_P_COUNTRY     = "P495"    # pays d'origine
_P_DURATION    = "P2047"   # durée en minutes
_P_BUDGET      = "P2130"   # budget (unité : Q4916 = dollar US)
_P_BOX_OFFICE  = "P2142"   # recettes mondiales

# ── Équipe créative ───────────────────────────────────────────
_P_DIRECTOR    = "P57"     # réalisateur
_P_SCREENWRITER= "P58"     # scénariste
_P_CAST        = "P161"    # acteur/actrice (qualifier P453 = nom du personnage)
_P_VOICE_ACTOR = "P725"    # acteur de doublage (animation)
_P_PRODUCER    = "P162"    # producteur
_P_EXEC_PROD   = "P1431"   # producteur exécutif
_P_PROD_CO     = "P272"    # société de production
_P_DISTRIBUTOR = "P750"    # distributeur
_P_CINEMATO    = "P344"    # directeur de la photographie (chef opérateur)
_P_EDITOR      = "P1040"   # monteur
_P_COMPOSER    = "P86"     # compositeur de la musique originale
_P_COST_DESIGN = "P2515"   # costumier
_P_PROD_DESIGN = "P2554"   # chef décorateur

# ── Lieux (encore référencés pour parsing des entités en recherche live) ──
_P_FILMING_LOC  = "P915"   # lieu de tournage réel (GPS via P625 sur l'entité lieu)
_P_NARRATIVE_LOC= "P840"   # lieu où se déroule l'intrigue (décor fictionnel)
_P_COORD        = "P625"   # coordonnées géographiques (lat/lng)

# ── Qualifiers utiles ─────────────────────────────────────────
_Q_CHARACTER   = "P453"    # qualifier sur P161 : nom du personnage joué

# ── Types de contenu ─────────────────────────────────────────
_FILM_TYPES = {"Q11424", "Q24862", "Q229390", "Q28026639"}
_TV_TYPES   = {"Q5398426", "Q21191270", "Q63952888", "Q842256", "Q220898"}
_DOC_TYPES  = {"Q93204", "Q4720177"}
_ALL_MEDIA  = _FILM_TYPES | _TV_TYPES | _DOC_TYPES

_RATE_DELAY = 0.8

# Cache mémoire pour les enrichissements (session serveur)
_enrichment_cache: dict = {}
_location_cache:   dict = {}

# ── Catalogue local de lieux de tournage ───────────────────────
# Chemins candidats, testés dans l'ordre (adapte _CATALOGUE_ENV_VAR
# ou ajoute ton chemin exact en tête de liste si besoin).
_CATALOGUE_ENV_VAR = "FILMING_CATALOGUE_PATH"
_CATALOGUE_CANDIDATES = [
    Path("catalogue_filming.json"),
    Path(__file__).resolve().parent / "catalogue_filming.json",
    Path(__file__).resolve().parent.parent / "catalogue_filming.json",
    Path(__file__).resolve().parent.parent / "data" / "catalogue_filming.json",
]

# Index construit une seule fois en mémoire :
#   {(tmdb_id, media_type): entry}  +  {tmdb_id: entry} (fallback si media_type diffère)
_catalogue_by_tmdb_type: dict[tuple[int, str], dict] = {}
_catalogue_by_tmdb_any:  dict[int, dict] = {}
_catalogue_loaded = False
_catalogue_path_used: Optional[Path] = None


def _resolve_catalogue_path() -> Optional[Path]:
    import os
    env_path = os.getenv(_CATALOGUE_ENV_VAR)
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    for candidate in _CATALOGUE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _load_catalogue(force: bool = False) -> None:
    """
    Charge catalogue_filming.json en mémoire (une seule fois, sauf force=True).
    Construit deux index pour lookup O(1) par (tmdb_id, media_type) et par tmdb_id seul.
    """
    global _catalogue_loaded, _catalogue_path_used
    global _catalogue_by_tmdb_type, _catalogue_by_tmdb_any

    if _catalogue_loaded and not force:
        return

    path = _resolve_catalogue_path()
    _catalogue_path_used = path

    if not path:
        print(
            f"⚠️ catalogue_filming.json introuvable "
            f"(vérifie {_CATALOGUE_ENV_VAR} ou place le fichier à la racine du projet)",
            flush=True,
        )
        _catalogue_by_tmdb_type = {}
        _catalogue_by_tmdb_any = {}
        _catalogue_loaded = True
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ catalogue_filming.json illisible ({path}): {str(e)[:80]}", flush=True)
        _catalogue_by_tmdb_type = {}
        _catalogue_by_tmdb_any = {}
        _catalogue_loaded = True
        return

    by_type: dict[tuple[int, str], dict] = {}
    by_any:  dict[int, dict] = {}

    entries = data if isinstance(data, list) else data.get("films", [])
    for entry in entries:
        tmdb_id = entry.get("tmdb_id")
        media_type = entry.get("media_type", "movie")
        if tmdb_id is None:
            continue
        try:
            tmdb_id = int(tmdb_id)
        except (TypeError, ValueError):
            continue
        by_type[(tmdb_id, media_type)] = entry
        # Fallback si un appelant passe le mauvais media_type
        by_any.setdefault(tmdb_id, entry)

    _catalogue_by_tmdb_type = by_type
    _catalogue_by_tmdb_any = by_any
    _catalogue_loaded = True

    print(
        f"📚 catalogue_filming.json chargé ({path}) → {len(by_type)} films indexés",
        flush=True,
    )


def reload_catalogue() -> None:
    """Force le rechargement du catalogue (utile après mise à jour du fichier sans redéploiement)."""
    _load_catalogue(force=True)
    _location_cache.clear()
    _enrichment_cache.clear()


def _lookup_catalogue_entry(tmdb_id: int, media_type: str = "movie") -> Optional[dict]:
    _load_catalogue()
    entry = _catalogue_by_tmdb_type.get((tmdb_id, media_type))
    if entry is None:
        entry = _catalogue_by_tmdb_any.get(tmdb_id)
    return entry


# ════════════════════════════════════════════════════════════════
# HELPERS PURS
# ════════════════════════════════════════════════════════════════

def _has_cjk(text: str) -> bool:
    return bool(re.search(r'[一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ가-힯]', text))


def _extract_year(time_str: str) -> Optional[int]:
    m = re.search(r'[+-]?(\d{4})', time_str)
    return int(m.group(1)) if m else None


def _claim_value(claims: dict, prop: str) -> Optional[str]:
    entries = claims.get(prop, [])
    if not entries:
        return None
    try:
        dv = entries[0]["mainsnak"]["datavalue"]["value"]
        return dv if isinstance(dv, str) else None
    except (KeyError, IndexError, TypeError):
        return None


def _claim_values(claims: dict, prop: str, limit: int = 10) -> list[str]:
    """Retourne toutes les valeurs string d'une propriété (ex : plusieurs pays)."""
    result = []
    for entry in claims.get(prop, [])[:limit]:
        try:
            dv = entry["mainsnak"]["datavalue"]["value"]
            if isinstance(dv, str):
                result.append(dv)
        except (KeyError, TypeError):
            pass
    return result


def _claim_qids(claims: dict, prop: str) -> list[str]:
    result = []
    for entry in claims.get(prop, []):
        try:
            dv = entry["mainsnak"]["datavalue"]["value"]
            if isinstance(dv, dict) and "id" in dv:
                result.append(dv["id"])
        except (KeyError, TypeError):
            pass
    return result


def _claim_time(claims: dict, prop: str) -> Optional[int]:
    entries = claims.get(prop, [])
    if not entries:
        return None
    try:
        time_str = entries[0]["mainsnak"]["datavalue"]["value"]["time"]
        return _extract_year(time_str)
    except (KeyError, IndexError, TypeError):
        return None


def _claim_quantity(claims: dict, prop: str) -> Optional[float]:
    """Retourne la valeur numérique d'une propriété quantitative (budget, durée...)."""
    entries = claims.get(prop, [])
    if not entries:
        return None
    try:
        amount = entries[0]["mainsnak"]["datavalue"]["value"]["amount"]
        return float(amount.lstrip("+"))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _claim_entity_with_qualifier(
    claims: dict,
    prop: str,
    qualifier_prop: str,
    limit: int = 8,
) -> list[dict]:
    """
    Retourne une liste d'entités avec leur qualifier.
    Exemple : P161 (acteur) + P453 (personnage) → [{qid, qualifier}]
    """
    result = []
    for entry in claims.get(prop, [])[:limit]:
        try:
            qid = entry["mainsnak"]["datavalue"]["value"]["id"]
            qualifier_val = None
            qualifiers = entry.get("qualifiers", {})
            if qualifier_prop in qualifiers:
                try:
                    q_dv = qualifiers[qualifier_prop][0]["datavalue"]["value"]
                    qualifier_val = q_dv.get("text") if isinstance(q_dv, dict) else str(q_dv)
                except (KeyError, IndexError, TypeError):
                    pass
            result.append({"qid": qid, "qualifier": qualifier_val})
        except (KeyError, TypeError):
            pass
    return result


def _resolve_media_type(instance_qids: list[str]) -> str:
    for qid in instance_qids:
        if qid in _FILM_TYPES or qid in _DOC_TYPES:
            return "movie"
        if qid in _TV_TYPES:
            return "tv"
    return "movie" if instance_qids else "unknown"


def _merge_cjk_lines(text: str) -> str:
    _CJK_LINE = re.compile(r'^[一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ가-힯\s]+$')
    lines = text.split("\n")
    merged: list[str] = []
    cjk_buf = ""
    for line in lines:
        stripped = line.strip()
        if stripped and _CJK_LINE.match(stripped):
            cjk_buf += stripped
        else:
            if cjk_buf:
                merged.append(cjk_buf)
                cjk_buf = ""
            merged.append(stripped)
    if cjk_buf:
        merged.append(cjk_buf)
    return "\n".join(merged)


# ════════════════════════════════════════════════════════════════
# APPELS API WIKIDATA (encore utilisés par la recherche par titre / CJK)
# ════════════════════════════════════════════════════════════════

async def _wd_search(query: str, lang: str = "en", limit: int = 5) -> list[dict]:
    params = {
        "action":   "wbsearchentities",
        "search":   query,
        "language": lang,
        "type":     "item",
        "format":   "json",
        "limit":    limit,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(_WD_API, params=params,
                                    headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            return resp.json().get("search", [])
    except Exception as e:
        print(f"⚠️ Wikidata search KO [{lang}] '{query[:30]}': {str(e)[:60]}", flush=True)
        return []


async def _wd_get_entities(qids: list[str], extra_props: str = "") -> dict:
    """
    Récupère les entités Wikidata.

    extra_props : propriétés supplémentaires à récupérer (ex: "sitelinks")
    Props récupérées par défaut : claims + labels + descriptions
    """
    if not qids:
        return {}
    props = "claims|labels|descriptions"
    if extra_props:
        props += "|" + extra_props

    params = {
        "action":    "wbgetentities",
        "ids":       "|".join(qids[:50]),
        "props":     props,
        "format":    "json",
        "languages": "en|fr|ja|ko|zh|de|es|it|ru|ar",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(_WD_API, params=params,
                                    headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            return resp.json().get("entities", {})
    except Exception as e:
        print(f"⚠️ Wikidata getentities KO: {str(e)[:60]}", flush=True)
        return {}


# ════════════════════════════════════════════════════════════════
# PARSING D'ENTITÉ — utilisé par la recherche par titre (live)
# ════════════════════════════════════════════════════════════════

def _parse_entity(qid: str, entity: dict) -> Optional[dict]:
    """
    Parse une entité Wikidata et extrait toutes les propriétés utiles.
    Retourne None si l'entité n'a pas d'ID TMDB ou IMDB (non exploitable).
    """
    claims = entity.get("claims", {})
    instance_qids = _claim_qids(claims, _P_INSTANCE_OF)
    media_type    = _resolve_media_type(instance_qids)

    tmdb_movie_id = _claim_value(claims, _P_TMDB_MOVIE)
    tmdb_tv_id    = _claim_value(claims, _P_TMDB_TV)
    imdb_id       = _claim_value(claims, _P_IMDB)
    eidr_id       = _claim_value(claims, _P_EIDR)

    if not tmdb_movie_id and not tmdb_tv_id and not imdb_id:
        return None

    if tmdb_tv_id and not tmdb_movie_id:
        media_type = "tv"
    elif tmdb_movie_id and not tmdb_tv_id and media_type == "unknown":
        media_type = "movie"

    tmdb_id = tmdb_movie_id or tmdb_tv_id
    year    = _claim_time(claims, _P_PUB_DATE)

    labels   = entity.get("labels", {})
    title_en = labels.get("en", {}).get("value", "")
    title_fr = labels.get("fr", {}).get("value", "")
    title_ja = labels.get("ja", {}).get("value", "")
    title_ko = labels.get("ko", {}).get("value", "")
    title_zh = labels.get("zh", {}).get("value", "")
    title_orig = title_ja or title_ko or title_zh or title_en

    country_qids   = _claim_qids(claims, _P_COUNTRY)
    orig_lang_qids = _claim_qids(claims, _P_ORIG_LANG)
    duration_min   = _claim_quantity(claims, _P_DURATION)
    budget         = _claim_quantity(claims, _P_BUDGET)
    box_office     = _claim_quantity(claims, _P_BOX_OFFICE)

    director_qids     = _claim_qids(claims, _P_DIRECTOR)
    screenwriter_qids = _claim_qids(claims, _P_SCREENWRITER)
    producer_qids     = _claim_qids(claims, _P_PRODUCER)
    prod_co_qids      = _claim_qids(claims, _P_PROD_CO)
    cinemato_qids     = _claim_qids(claims, _P_CINEMATO)
    editor_qids       = _claim_qids(claims, _P_EDITOR)
    composer_qids     = _claim_qids(claims, _P_COMPOSER)
    distributor_qids  = _claim_qids(claims, _P_DISTRIBUTOR)

    cast_with_chars   = _claim_entity_with_qualifier(claims, _P_CAST,       _Q_CHARACTER, limit=6)
    voice_with_chars  = _claim_entity_with_qualifier(claims, _P_VOICE_ACTOR, _Q_CHARACTER, limit=6)

    filming_loc_qids   = _claim_qids(claims, _P_FILMING_LOC)
    narrative_loc_qids = _claim_qids(claims, _P_NARRATIVE_LOC)

    return {
        "wikidata_id":         qid,
        "tmdb_id":             int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None,
        "imdb_id":             imdb_id,
        "eidr_id":             eidr_id,
        "media_type":          media_type,
        "year":                year,
        "title_en":            title_en,
        "title_fr":            title_fr,
        "title_ja":            title_ja,
        "title_ko":            title_ko,
        "title_zh":            title_zh,
        "title_orig":          title_orig,
        "country_qids":        country_qids[:3],
        "orig_lang_qids":      orig_lang_qids[:2],
        "duration_min":        int(duration_min) if duration_min else None,
        "budget_usd":          int(budget) if budget else None,
        "box_office_usd":      int(box_office) if box_office else None,
        "director_qids":       director_qids[:3],
        "screenwriter_qids":   screenwriter_qids[:3],
        "producer_qids":       producer_qids[:3],
        "prod_co_qids":        prod_co_qids[:3],
        "cinemato_qids":       cinemato_qids[:2],
        "editor_qids":         editor_qids[:2],
        "composer_qids":       composer_qids[:2],
        "distributor_qids":    distributor_qids[:3],
        "cast_with_chars":     cast_with_chars,
        "voice_with_chars":    voice_with_chars,
        "filming_loc_qids":    filming_loc_qids[:8],
        "narrative_loc_qids":  narrative_loc_qids[:4],
    }


# ════════════════════════════════════════════════════════════════
# LIEUX DE TOURNAGE — 100% LOCAL (catalogue_filming.json)
# ════════════════════════════════════════════════════════════════

async def get_filming_locations(tmdb_id: int, media_type: str = "movie") -> list[dict]:
    """
    Retourne les lieux de tournage d'un film depuis catalogue_filming.json.
    Aucun appel réseau. Fonction gardée `async` pour compatibilité avec
    les appelants existants (elle est instantanée en pratique).

    Retourne :
      [{"name": "Los Angeles", "lat": 34.05, "lng": -118.24,
        "wikidata_id": "Q65", "city": "...", "country": "..."}]
    """
    cache_key = f"{tmdb_id}_{media_type}"
    if cache_key in _location_cache:
        return _location_cache[cache_key]

    entry = _lookup_catalogue_entry(tmdb_id, media_type)
    if not entry:
        print(f"📍 tmdb_id={tmdb_id} absent du catalogue local", flush=True)
        _location_cache[cache_key] = []
        return []

    raw_locations = entry.get("locations", [])
    locations: list[dict] = []
    for loc in raw_locations:
        locations.append({
            "name":        loc.get("name") or loc.get("wikidata_id", "?"),
            "lat":         loc.get("lat"),
            "lng":         loc.get("lng"),
            "wikidata_id": loc.get("wikidata_id"),
            "city":        loc.get("city"),
            "country":     loc.get("country"),
        })

    print(
        f"📍 {len(locations)} lieux (catalogue local) pour tmdb_id={tmdb_id}",
        flush=True,
    )
    _location_cache[cache_key] = locations
    return locations


# ════════════════════════════════════════════════════════════════
# ENRICHISSEMENT — 100% LOCAL (crew/cast/EIDR volontairement vides)
# ════════════════════════════════════════════════════════════════

async def get_wikidata_enrichment(tmdb_id: int, media_type: str = "movie") -> dict:
    """
    Enrichissement d'une fiche film — désormais basé uniquement sur
    catalogue_filming.json. Aucun appel réseau vers Wikidata.

    Le catalogue local ne contenant que titre/tmdb_id/locations,
    crew/cast_wd/eidr_id/budget_usd/box_office_usd sont renvoyés vides.
    Si tu as besoin de ces champs, il faudra soit enrichir le catalogue
    JSON hors-ligne, soit réactiver un appel live ciblé.
    """
    cache_key = f"{tmdb_id}_{media_type}"
    if cache_key in _enrichment_cache:
        return _enrichment_cache[cache_key]

    empty = {
        "crew": {}, "companies": [], "cast_wd": [],
        "locations": [], "eidr_id": None,
        "budget_usd": None, "box_office_usd": None,
        "wikidata_id": None, "duration_min": None,
    }

    entry = _lookup_catalogue_entry(tmdb_id, media_type)
    if not entry:
        _enrichment_cache[cache_key] = empty
        return empty

    locations = await get_filming_locations(tmdb_id, media_type)

    result = {
        "crew":           {},
        "companies":      [],
        "cast_wd":        [],
        "locations":      locations,
        "eidr_id":        None,
        "budget_usd":     None,
        "box_office_usd": None,
        "wikidata_id":    entry.get("wikidata_id"),
        "duration_min":   None,
    }

    _enrichment_cache[cache_key] = result
    print(
        f"✅ Enrichment local OK (tmdb_id={tmdb_id}): {len(locations)} lieux "
        f"— crew/cast/EIDR non disponibles (catalogue local)",
        flush=True,
    )
    return result


# ════════════════════════════════════════════════════════════════
# ENRICHISSEMENT TMDB / CANDIDATS (recherche par titre — reste live)
# ════════════════════════════════════════════════════════════════

async def _enrich_via_tmdb(wd_result: dict, browser_lang: str = "fr") -> Optional[dict]:
    from data.tmdb import get_movie_details, get_tv_details
    tmdb_id    = wd_result.get("tmdb_id")
    media_type = wd_result.get("media_type", "movie")
    if not tmdb_id:
        return None
    try:
        details = (
            await get_tv_details(tmdb_id, browser_lang)
            if media_type == "tv"
            else await get_movie_details(tmdb_id, browser_lang)
        )
        return {
            "id":           tmdb_id,
            "media_type":   media_type,
            "title":        details.get("title") or details.get("name", ""),
            "name":         details.get("name", ""),
            "popularity":   details.get("popularity", 0),
            "vote_average": details.get("vote_average", 0),
            "genre_ids":    [g["id"] for g in details.get("genres", [])],
            "release_date": details.get("release_date") or details.get("first_air_date", ""),
            "overview":     details.get("overview", ""),
            "poster_path":  details.get("poster_path", ""),
            "_wikidata_id": wd_result.get("wikidata_id"),
            "_imdb_id":     wd_result.get("imdb_id"),
            "_eidr_id":     wd_result.get("eidr_id"),
            "_source":      "wikidata",
        }
    except Exception as e:
        print(f"⚠️ TMDB enrich KO (id={tmdb_id}): {str(e)[:60]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# CONSTRUCTION DES REQUÊTES (recherche par titre — reste live)
# ════════════════════════════════════════════════════════════════

def _build_wikidata_queries(extraction: dict, ocr_text: str = "") -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []

    titres_certains = [
        str(t).strip()
        for t in extraction.get("titres_possibles", [])
        if not str(t).startswith("?") and str(t).strip()
    ]
    titres_incertains = [
        str(t)[1:].strip()
        for t in extraction.get("titres_possibles", [])
        if str(t).startswith("?") and len(str(t)) > 2
    ]

    ocr = _merge_cjk_lines((ocr_text or "").strip())
    cjk_seqs     = re.findall(r'[一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ가-힯]{2,}', ocr)
    has_hiragana = bool(re.search(r'[぀-ゟ゠-ヿ]', ocr))
    has_hangul   = bool(re.search(r'[가-힯]', ocr))
    has_cjk      = bool(re.search(r'[一-鿿]', ocr))

    for seq in cjk_seqs[:2]:
        if has_hiragana or (has_cjk and not has_hangul):
            queries.append((seq, "ja"))
            queries.append((seq, "zh"))
        elif has_hangul:
            queries.append((seq, "ko"))
        else:
            queries.append((seq, "zh"))
            queries.append((seq, "zh-hans"))

    for titre in titres_certains[:2]:
        if _has_cjk(titre):
            lang = "ja" if re.search(r'[぀-ゟ゠-ヿ]', titre) else "zh"
            queries.append((titre, lang))
        else:
            queries.append((titre, "en"))
            queries.append((titre, "fr"))

    for titre in titres_incertains[:2]:
        if _has_cjk(titre):
            lang = "ja" if re.search(r'[぀-ゟ゠-ヿ]', titre) else "zh"
            queries.append((titre, lang))
        else:
            queries.append((titre, "en"))

    seen: set = set()
    result: list[tuple[str, str]] = []
    for q, l in queries:
        key = f"{q}|{l}"
        if key not in seen and q and len(q) > 1:
            seen.add(key)
            result.append((q, l))
        if len(result) >= 6:
            break

    return result


# ════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL (identification par titre — reste live)
# ════════════════════════════════════════════════════════════════

async def wikidata_search_candidates(
    extraction: dict,
    ocr_text: str = "",
    browser_lang: str = "fr",
    omdb_api_key: str = "",
    max_candidates: int = 10,
) -> list[dict]:
    """
    Pipeline complet Wikidata → TMDB candidats (recherche par titre, CJK/coréen).
    Reste en LIVE (wbsearchentities/wbgetentities) — pas de SPARQL, donc pas
    concerné par le problème de 429 qui touchait les lieux de tournage.
    """
    print("🌐 Wikidata search démarré...", flush=True)

    queries = _build_wikidata_queries(extraction, ocr_text)
    if not queries:
        print("🌐 Wikidata: aucune requête générée", flush=True)
        return []

    print(f"🌐 Wikidata queries ({len(queries)}): {queries}", flush=True)

    all_qids: list[str] = []
    seen_qids: set = set()

    for i, (query, lang) in enumerate(queries):
        results = await _wd_search(query, lang=lang, limit=5)
        for r in results:
            qid = r.get("id", "")
            if qid and qid not in seen_qids:
                seen_qids.add(qid)
                all_qids.append(qid)
                print(
                    f"  📖 [{lang}] '{query[:30]}' → {qid} "
                    f"({r.get('label','?')}: {r.get('description','')[:50]})",
                    flush=True
                )
        if i < len(queries) - 1:
            await asyncio.sleep(_RATE_DELAY)

    if not all_qids:
        print("🌐 Wikidata: aucun QID trouvé", flush=True)
        return []

    print(f"🌐 {len(all_qids)} QIDs → récupération des claims...", flush=True)

    await asyncio.sleep(_RATE_DELAY)
    entities = await _wd_get_entities(all_qids)

    parsed: list[dict] = []
    for qid in all_qids:
        entity = entities.get(qid, {})
        if not entity or entity.get("missing"):
            continue
        result = _parse_entity(qid, entity)
        if result:
            parsed.append(result)
            print(
                f"  ✅ {qid} → tmdb={result.get('tmdb_id')} "
                f"imdb={result.get('imdb_id')} eidr={result.get('eidr_id')} "
                f"type={result.get('media_type')} year={result.get('year')} "
                f"lieux={len(result.get('filming_loc_qids', []))} "
                f"'{result.get('title_en') or result.get('title_orig')}'",
                flush=True
            )

    if not parsed:
        print("🌐 Wikidata: aucune entité avec IDs exploitables", flush=True)
        return []

    candidates: list[dict] = []
    seen_ids: set = set()

    tmdb_tasks = []
    for wd in parsed:
        if wd.get("tmdb_id") and wd["tmdb_id"] not in seen_ids:
            seen_ids.add(wd["tmdb_id"])
            tmdb_tasks.append(_enrich_via_tmdb(wd, browser_lang))

    if tmdb_tasks:
        await asyncio.sleep(_RATE_DELAY)
        results = await asyncio.gather(*tmdb_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict) and r:
                candidates.append(r)

    for wd in parsed:
        if not wd.get("tmdb_id") and len(candidates) < max_candidates:
            title = wd.get("title_en") or wd.get("title_orig")
            if title:
                from data.tmdb import search_multi_lang
                try:
                    tmdb_results = await search_multi_lang(
                        title,
                        transcript_lang=None,
                        browser_lang=browser_lang,
                    )
                    for item in tmdb_results[:2]:
                        if item.get("id") not in {c.get("id") for c in candidates}:
                            item["_source"] = "wikidata_title"
                            candidates.append(item)
                except Exception:
                    pass

    candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    print(
        f"Wikidata → {len(candidates)} candidats TMDB "
        f"(depuis {len(parsed)} entités)",
        flush=True
    )
    return candidates[:max_candidates]


# ════════════════════════════════════════════════════════════════
# TRIGGER
# ════════════════════════════════════════════════════════════════

def should_trigger_wikidata(
    score: int,
    extraction: dict,
    ocr_text: str = "",
) -> bool:
    combined = (ocr_text or "") + " ".join(
        str(t) for t in extraction.get("titres_possibles", [])
    )
    if re.search(r'[一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ가-힯]', combined):
        print("🌐 Trigger Wikidata: caractères CJK/coréens détectés", flush=True)
        return True

    if score < 40:
        lang = (extraction.get("langue_originale") or "").lower()
        non_latin = {"ja", "ko", "zh", "ar", "hi", "th", "ru", "he", "fa", "tr", "vi"}
        if lang in non_latin:
            print(f"🌐 Trigger Wikidata: score faible ({score}) + langue {lang}", flush=True)
            return True

    return False