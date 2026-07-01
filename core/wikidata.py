"""
core/wikidata.py — Recherche et enrichissement de films via Wikidata.

Couche 2 du pipeline de recherche, entre la cascade TMDB (couche 1)
et le web search DDG (couche 3).

Pourquoi Wikidata en complément de TMDB ?
  - Couverture mondiale : films japonais/coréens/chinois des années 1920-2025
  - Titres originaux en kanji/hangeul/caractères chinois indexés nativement
  - Retourne les IDs TMDB et IMDB → enrichissement sans dupliquer les données
  - Données exclusives : lieux de tournage GPS, équipe créative complète, EIDR
  - Gratuit, sans clé API, sans limite stricte (respecter ~1 req/s)

Nouvelles propriétés extraites (v2) :
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
  1. wikidata_search(titre, lang)       → liste de QIDs + labels
  2. wikidata_get_ids(qid)              → {tmdb_id, imdb_id, tmdb_type, year, lang, ...}
  3. wikidata_to_tmdb_candidates()      → pipeline complet → candidats TMDB normalisés
  4. get_filming_locations(tmdb_id)     → [{name, lat, lng, wikidata_id}] depuis QID film
  5. get_wikidata_enrichment(tmdb_id)   → dict complet crew/lieux/EIDR pour une fiche film

Rate limiting : 0.8s entre les appels (Wikimedia policy = max 1 req/s anonyme)
"""

import asyncio
import re
from typing import Optional

import httpx
# core/wikidata.py
# Ajouter ces imports en haut (après les imports existants)

from storage.cache_engine.redis_client import get_redis
from storage.cache_engine.ttl import DAY

_WD_QID_TTL = 30 * DAY

# ════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════

_WD_API     = "https://www.wikidata.org/w/api.php"
_WD_SPARQL  = "https://query.wikidata.org/sparql"
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

# ── Lieux ─────────────────────────────────────────────────────
_P_FILMING_LOC = "P915"    # lieu de tournage réel (GPS via P625 sur l'entité lieu)
_P_NARRATIVE_LOC= "P840"   # lieu où se déroule l'intrigue (décor fictionnel)
_P_COORD       = "P625"    # coordonnées géographiques (lat/lng)

# ── Qualifiers utiles ─────────────────────────────────────────
_Q_CHARACTER   = "P453"    # qualifier sur P161 : nom du personnage joué

# ── Types de contenu ─────────────────────────────────────────
_FILM_TYPES = {"Q11424", "Q24862", "Q229390", "Q28026639"}
_TV_TYPES   = {"Q5398426", "Q21191270", "Q63952888", "Q842256", "Q220898"}
_DOC_TYPES  = {"Q93204", "Q4720177"}
_ALL_MEDIA  = _FILM_TYPES | _TV_TYPES | _DOC_TYPES

_RATE_DELAY = 0.8

# Cache mémoire pour les enrichissements (évite de re-requêter Wikidata
# pour le même film plusieurs fois dans la même session serveur)
_enrichment_cache: dict = {}
_location_cache:   dict = {}


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
# APPELS API WIKIDATA
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


async def _wd_get_entity_label(qid: str) -> str:
    """Récupère le label anglais d'une entité (ex: nom d'une personne ou d'un lieu)."""
    entities = await _wd_get_entities([qid])
    entity = entities.get(qid, {})
    labels = entity.get("labels", {})
    return (
        labels.get("en", {}).get("value")
        or labels.get("fr", {}).get("value")
        or labels.get("ja", {}).get("value")
        or qid
    )


async def _wd_get_coord(place_qid: str) -> Optional[tuple[float, float]]:
    """
    Récupère les coordonnées GPS d'une entité lieu via P625.
    Retourne (lat, lng) ou None.
    """
    entities = await _wd_get_entities([place_qid])
    entity   = entities.get(place_qid, {})
    claims   = entity.get("claims", {})
    coord_entries = claims.get(_P_COORD, [])
    if not coord_entries:
        return None
    try:
        val = coord_entries[0]["mainsnak"]["datavalue"]["value"]
        return (val["latitude"], val["longitude"])
    except (KeyError, IndexError, TypeError):
        return None

async def _find_wikidata_qid_by_tmdb(tmdb_id: int, media_type: str = "movie") -> Optional[str]:
    """
    Retrouve le QID Wikidata d'un film à partir de son ID TMDB.
    Utilise SPARQL pour la recherche inverse.
    Fix v2 :
    - Cache Redis 30 jours (clé wd:qid:{tmdb_id}:{media_type})
      → évite de retaper Wikidata pour les fiches déjà vues
    - Retry unique sur 429 avec backoff 65s
      → Wikidata rate-limit = 1 req/min anonyme, 65s suffit
    - Valeur sentinelle "" mise en cache quand QID introuvable
      → évite de retenter indéfiniment pour les films sans entrée Wikidata
    - Cache immédiat sur 429 (TTL 10 min)
      → bloque les requêtes concurrentes sur le même tmdb_id pendant le sleep
    """
    cache_key = f"wd:qid:{tmdb_id}:{media_type}"

    # ── Lecture cache Redis ──────────────────────────────────────────────
    redis = get_redis()
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached is not None:
                # "" = sentinelle "connu comme absent"
                return cached if cached else None
        except Exception as e:
            print(f"⚠️ Redis read KO (wikidata qid): {e}", flush=True)

    prop  = _P_TMDB_MOVIE if media_type == "movie" else _P_TMDB_TV
    query = f"""
    SELECT ?item WHERE {{
      ?item wdt:{prop} "{tmdb_id}" .
    }}
    LIMIT 1
    """

    async def _do_sparql() -> Optional[str]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _WD_SPARQL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            if resp.status_code == 429:
                return "429"
            resp.raise_for_status()
            bindings = resp.json().get("results", {}).get("bindings", [])
            if bindings:
                return bindings[0]["item"]["value"].split("/")[-1]
            return None

    qid = None
    try:
        result = await _do_sparql()

        # ── Retry sur 429 avec backoff 65s ────────────────────────────
        if result == "429":
            print(
                f" SPARQL 429 (tmdb={tmdb_id}) → attente 65s puis retry...",
                flush=True
            )
            # Cache immédiat de la sentinelle pour bloquer les requêtes
            # concurrentes sur le même tmdb_id pendant le sleep.
            # TTL court (10 min) : sera écrasé par le vrai résultat après retry.
            if redis:
                try:
                    redis.set(cache_key, "", ex=600)
                except Exception:
                    pass
            await asyncio.sleep(65)
            try:
                result = await _do_sparql()
                if result == "429":
                    print(
                        f" SPARQL 429 persistant (tmdb={tmdb_id}) → abandon",
                        flush=True
                    )
                    result = None
            except Exception as e2:
                print(f" SPARQL retry KO (tmdb={tmdb_id}): {str(e2)[:60]}", flush=True)
                result = None

        qid = result if result != "429" else None

    except Exception as e:
        print(f" SPARQL inverse KO (tmdb={tmdb_id}): {str(e)[:60]}", flush=True)
        qid = None

    # ── Écriture cache Redis ─────────────────────────────────────────────
    # On cache aussi l'absence (sentinelle "") pour ne pas retenter.
    # Si le retry a réussi, ce set écrase le TTL court de 600s par le TTL long.
    if redis:
        try:
            redis.set(cache_key, qid or "", ex=_WD_QID_TTL)
        except Exception as e:
            print(f" Redis write KO (wikidata qid): {e}", flush=True)

    return qid

# ════════════════════════════════════════════════════════════════
# PARSING D'ENTITÉ — VERSION ENRICHIE
# ════════════════════════════════════════════════════════════════

def _parse_entity(qid: str, entity: dict) -> Optional[dict]:
    """
    Parse une entité Wikidata et extrait toutes les propriétés utiles.

    Retourne None si l'entité n'a pas d'ID TMDB ou IMDB (non exploitable).
    """
    claims = entity.get("claims", {})
    instance_qids = _claim_qids(claims, _P_INSTANCE_OF)
    media_type    = _resolve_media_type(instance_qids)

    # ── Identifiants externes ─────────────────────────────────
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

    # ── Titres multilingues ───────────────────────────────────
    labels   = entity.get("labels", {})
    title_en = labels.get("en", {}).get("value", "")
    title_fr = labels.get("fr", {}).get("value", "")
    title_ja = labels.get("ja", {}).get("value", "")
    title_ko = labels.get("ko", {}).get("value", "")
    title_zh = labels.get("zh", {}).get("value", "")
    title_orig = title_ja or title_ko or title_zh or title_en

    # ── Métadonnées ───────────────────────────────────────────
    # Pays d'origine : liste de QIDs → on garde les QIDs pour résolution ultérieure
    country_qids   = _claim_qids(claims, _P_COUNTRY)
    orig_lang_qids = _claim_qids(claims, _P_ORIG_LANG)
    duration_min   = _claim_quantity(claims, _P_DURATION)
    budget         = _claim_quantity(claims, _P_BUDGET)
    box_office     = _claim_quantity(claims, _P_BOX_OFFICE)

    # ── Équipe créative (QIDs uniquement — labels résolus à la demande) ──
    director_qids     = _claim_qids(claims, _P_DIRECTOR)
    screenwriter_qids = _claim_qids(claims, _P_SCREENWRITER)
    producer_qids     = _claim_qids(claims, _P_PRODUCER)
    prod_co_qids      = _claim_qids(claims, _P_PROD_CO)
    cinemato_qids     = _claim_qids(claims, _P_CINEMATO)
    editor_qids       = _claim_qids(claims, _P_EDITOR)
    composer_qids     = _claim_qids(claims, _P_COMPOSER)
    distributor_qids  = _claim_qids(claims, _P_DISTRIBUTOR)

    # Cast avec qualifier personnage
    cast_with_chars   = _claim_entity_with_qualifier(claims, _P_CAST,       _Q_CHARACTER, limit=6)
    voice_with_chars  = _claim_entity_with_qualifier(claims, _P_VOICE_ACTOR, _Q_CHARACTER, limit=6)

    # ── Lieux ─────────────────────────────────────────────────
    filming_loc_qids  = _claim_qids(claims, _P_FILMING_LOC)   # lieux réels de tournage
    narrative_loc_qids = _claim_qids(claims, _P_NARRATIVE_LOC) # décors fictionnels

    return {
        "wikidata_id":         qid,
        "tmdb_id":             int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None,
        "imdb_id":             imdb_id,
        "eidr_id":             eidr_id,
        "media_type":          media_type,
        "year":                year,
        # Titres
        "title_en":            title_en,
        "title_fr":            title_fr,
        "title_ja":            title_ja,
        "title_ko":            title_ko,
        "title_zh":            title_zh,
        "title_orig":          title_orig,
        # Métadonnées
        "country_qids":        country_qids[:3],
        "orig_lang_qids":      orig_lang_qids[:2],
        "duration_min":        int(duration_min) if duration_min else None,
        "budget_usd":          int(budget) if budget else None,
        "box_office_usd":      int(box_office) if box_office else None,
        # Équipe créative (QIDs — résolus via _resolve_crew_labels)
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
        # Lieux
        "filming_loc_qids":    filming_loc_qids[:8],
        "narrative_loc_qids":  narrative_loc_qids[:4],
    }


# ════════════════════════════════════════════════════════════════
# RÉSOLUTION DES LABELS D'ÉQUIPE CRÉATIVE
# ════════════════════════════════════════════════════════════════

async def _resolve_crew_labels(wd_result: dict) -> dict:
    """
    Résout les QIDs de l'équipe créative en noms lisibles.
    Appelé en batch pour éviter N+1 requêtes.
    Retourne un dict {qid: name}.
    """
    all_qids: list[str] = []
    for key in (
        "director_qids", "screenwriter_qids", "producer_qids",
        "prod_co_qids", "cinemato_qids", "editor_qids",
        "composer_qids", "distributor_qids",
    ):
        all_qids += wd_result.get(key, [])

    for item in wd_result.get("cast_with_chars", []) + wd_result.get("voice_with_chars", []):
        qid = item.get("qid")
        if qid:
            all_qids.append(qid)

    all_qids = list(dict.fromkeys(all_qids))[:40]  # dédoublonnage, max 40

    if not all_qids:
        return {}

    entities = await _wd_get_entities(all_qids)
    result: dict[str, str] = {}
    for qid in all_qids:
        entity = entities.get(qid, {})
        labels = entity.get("labels", {})
        name = (
            labels.get("en", {}).get("value")
            or labels.get("fr", {}).get("value")
            or labels.get("ja", {}).get("value")
            or labels.get("ko", {}).get("value")
            or qid
        )
        result[qid] = name

    return result


# ════════════════════════════════════════════════════════════════
# LIEUX DE TOURNAGE (FEATURE PRINCIPALE V2)
# ════════════════════════════════════════════════════════════════

async def get_filming_locations(tmdb_id: int, media_type: str = "movie") -> list[dict]:
    """
    Retourne les lieux de tournage d'un film avec coordonnées GPS.

    Flux :
      1. Recherche du QID Wikidata par ID TMDB (SPARQL inverse)
      2. Récupération de P915 (filming_location) → liste de QIDs de lieux
      3. Résolution GPS via P625 sur chaque lieu (en parallèle)

    Retourne :
      [{"name": "Château de Pierrefonds", "lat": 49.35, "lng": 2.98, "wikidata_id": "Q1234"}]

    Cache mémoire : les lieux sont mis en cache par tmdb_id pour la durée de la session.
    """
    cache_key = f"{tmdb_id}_{media_type}"
    if cache_key in _location_cache:
        return _location_cache[cache_key]

    print(f"📍 Wikidata filming locations pour tmdb_id={tmdb_id}...", flush=True)

    # Étape 1 : QID du film
    qid = await _find_wikidata_qid_by_tmdb(tmdb_id, media_type)
    if not qid:
        print(f"📍 Aucun QID Wikidata trouvé pour tmdb_id={tmdb_id}", flush=True)
        _location_cache[cache_key] = []
        return []

    await asyncio.sleep(_RATE_DELAY)

    # Étape 2 : entité du film → P915
    entities = await _wd_get_entities([qid])
    entity   = entities.get(qid, {})
    claims   = entity.get("claims", {})
    loc_qids = _claim_qids(claims, _P_FILMING_LOC)[:8]

    if not loc_qids:
        print(f"📍 Aucun lieu de tournage pour {qid}", flush=True)
        _location_cache[cache_key] = []
        return []

    print(f"📍 {len(loc_qids)} lieux trouvés pour {qid}: {loc_qids}", flush=True)

    # Étape 3 : labels + coordonnées en batch
    await asyncio.sleep(_RATE_DELAY)
    loc_entities = await _wd_get_entities(loc_qids)

    locations: list[dict] = []
    for loc_qid in loc_qids:
        loc_entity = loc_entities.get(loc_qid, {})
        if not loc_entity or loc_entity.get("missing"):
            continue

        loc_labels = loc_entity.get("labels", {})
        name = (
            loc_labels.get("fr", {}).get("value")
            or loc_labels.get("en", {}).get("value")
            or loc_labels.get("de", {}).get("value")
            or loc_labels.get("es", {}).get("value")
            or loc_qid
        )

        loc_claims = loc_entity.get("claims", {})
        coord_entries = loc_claims.get(_P_COORD, [])
        lat, lng = None, None
        if coord_entries:
            try:
                val = coord_entries[0]["mainsnak"]["datavalue"]["value"]
                lat = val.get("latitude")
                lng = val.get("longitude")
            except (KeyError, IndexError, TypeError):
                pass

        if lat is not None and lng is not None:
            locations.append({
                "name":        name,
                "lat":         lat,
                "lng":         lng,
                "wikidata_id": loc_qid,
            })
        else:
            # Lieu sans coordonnées → on l'inclut quand même (pour affichage texte)
            locations.append({
                "name":        name,
                "lat":         None,
                "lng":         None,
                "wikidata_id": loc_qid,
            })

    print(f"✅ {len(locations)} lieux résolus (dont {sum(1 for l in locations if l['lat'])} avec GPS)", flush=True)
    _location_cache[cache_key] = locations
    return locations


# ════════════════════════════════════════════════════════════════
# ENRICHISSEMENT COMPLET (FICHE DÉTAIL)
# ════════════════════════════════════════════════════════════════

async def get_wikidata_enrichment(tmdb_id: int, media_type: str = "movie") -> dict:
    """
    Enrichissement complet d'une fiche film depuis Wikidata.
    À appeler depuis /movie/{id} pour compléter les données TMDB.

    Retourne un dict avec :
      - crew       : {directors, screenwriters, producers, cinematographers, editors, composers}
      - companies  : [{name}]
      - cast_wd    : [{name, character}]  ← cast Wikidata (souvent plus complet pour films anciens)
      - locations  : [{name, lat, lng, wikidata_id}]
      - eidr_id    : str | None           ← identifiant standard industrie
      - budget_usd : int | None
      - box_office_usd : int | None
      - wikidata_id    : str | None
    """
    cache_key = f"{tmdb_id}_{media_type}"
    if cache_key in _enrichment_cache:
        return _enrichment_cache[cache_key]

    print(f"🌐 Wikidata enrichment pour tmdb_id={tmdb_id}...", flush=True)

    empty = {
        "crew": {}, "companies": [], "cast_wd": [],
        "locations": [], "eidr_id": None,
        "budget_usd": None, "box_office_usd": None,
        "wikidata_id": None,
    }

    # Étape 1 : QID inverse
    qid = await _find_wikidata_qid_by_tmdb(tmdb_id, media_type)
    if not qid:
        _enrichment_cache[cache_key] = empty
        return empty

    await asyncio.sleep(_RATE_DELAY)

    # Étape 2 : entité complète
    entities = await _wd_get_entities([qid])
    entity   = entities.get(qid, {})
    if not entity or entity.get("missing"):
        _enrichment_cache[cache_key] = empty
        return empty

    parsed = _parse_entity(qid, entity)
    if not parsed:
        _enrichment_cache[cache_key] = empty
        return empty

    await asyncio.sleep(_RATE_DELAY)

    # Étape 3 : résolution des labels de l'équipe en batch
    label_map = await _resolve_crew_labels(parsed)

    def _resolve(qids: list[str]) -> list[str]:
        return [label_map.get(q, q) for q in qids if q]

    crew = {
        "directors":       _resolve(parsed.get("director_qids", [])),
        "screenwriters":   _resolve(parsed.get("screenwriter_qids", [])),
        "producers":       _resolve(parsed.get("producer_qids", [])),
        "cinematographers":_resolve(parsed.get("cinemato_qids", [])),
        "editors":         _resolve(parsed.get("editor_qids", [])),
        "composers":       _resolve(parsed.get("composer_qids", [])),
        "distributors":    _resolve(parsed.get("distributor_qids", [])),
    }

    companies = [
        {"name": label_map.get(q, q)}
        for q in parsed.get("prod_co_qids", [])
    ]

    cast_wd = [
        {
            "name":      label_map.get(item["qid"], item["qid"]),
            "character": item.get("qualifier"),
        }
        for item in (parsed.get("cast_with_chars", []) + parsed.get("voice_with_chars", []))
        if item.get("qid")
    ]

    # Étape 4 : lieux de tournage (réutilise le cache si déjà chargé)
    locations = await get_filming_locations(tmdb_id, media_type)

    result = {
        "crew":           crew,
        "companies":      companies,
        "cast_wd":        cast_wd,
        "locations":      locations,
        "eidr_id":        parsed.get("eidr_id"),
        "budget_usd":     parsed.get("budget_usd"),
        "box_office_usd": parsed.get("box_office_usd"),
        "wikidata_id":    qid,
        "duration_min":   parsed.get("duration_min"),
    }

    _enrichment_cache[cache_key] = result
    print(
        f"✅ Wikidata enrichment OK: {len(crew.get('directors',[]))} réal, "
        f"{len(cast_wd)} acteurs, {len(locations)} lieux, "
        f"EIDR={parsed.get('eidr_id') or 'N/A'}",
        flush=True
    )
    return result


# ════════════════════════════════════════════════════════════════
# ENRICHISSEMENT TMDB / CANDIDATS
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
# CONSTRUCTION DES REQUÊTES
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
# PIPELINE PRINCIPAL (identification)
# ════════════════════════════════════════════════════════════════

async def wikidata_search_candidates(
    extraction: dict,
    ocr_text: str = "",
    browser_lang: str = "fr",
    omdb_api_key: str = "",
    max_candidates: int = 10,
) -> list[dict]:
    """
    Pipeline complet Wikidata → TMDB candidats.

    Étapes :
      1. Construire les requêtes depuis OCR CJK + titres Gemini
      2. wbsearchentities → QIDs
      3. wbgetentities → TMDB/IMDB IDs + métadonnées enrichies
      4. Enrichir via TMDB (get_movie_details / get_tv_details)
      5. Retourner candidats normalisés pour rerank()
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
        f"✅ Wikidata → {len(candidates)} candidats TMDB "
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