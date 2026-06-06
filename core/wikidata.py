"""
core/wikidata.py — Recherche de films via Wikidata.

Couche 2 du pipeline de recherche, entre la cascade TMDB (couche 1)
et le web search DDG (couche 3).

Pourquoi Wikidata en complément de TMDB ?
  - Couverture mondiale : films japonais/coréens/chinois des années 1920-2025
  - Titres originaux en kanji/hangeul/caractères chinois indexés nativement
  - Retourne les IDs TMDB et IMDB → enrichissement sans dupliquer les données
  - Gratuit, sans clé API, sans limite stricte (respecter ~1 req/s)

Architecture :
  1. wikidata_search(titre, lang)  → liste de QIDs + labels
  2. wikidata_get_ids(qid)         → {tmdb_id, imdb_id, tmdb_type, year, lang}
  3. wikidata_to_tmdb_candidates() → pipeline complet → candidats TMDB normalisés

Types Wikidata supportés :
  Q11424   = film long métrage      Q24862   = court métrage
  Q5398426 = série télévisée        Q63952888= série animée / anime
  Q93204   = documentaire           Q229390  = film d'animation
  Q842256  = OVA

Rate limiting : 0.8s entre les appels (Wikimedia policy = max 1 req/s anonyme)
"""

import asyncio
import re
from typing import Optional

import httpx

# ════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════

_WD_API    = "https://www.wikidata.org/w/api.php"
_USER_AGENT = "ShadowFrame/1.0 (film identification; https://quelfilm.app)"

_P_INSTANCE_OF = "P31"
_P_TMDB_MOVIE  = "P4947"
_P_TMDB_TV     = "P4983"
_P_IMDB        = "P345"
_P_PUB_DATE    = "P577"

_FILM_TYPES = {"Q11424", "Q24862", "Q229390", "Q28026639"}
_TV_TYPES   = {"Q5398426", "Q21191270", "Q63952888", "Q842256", "Q220898"}
_DOC_TYPES  = {"Q93204", "Q4720177"}
_ALL_MEDIA  = _FILM_TYPES | _TV_TYPES | _DOC_TYPES

_RATE_DELAY = 0.8


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


def _resolve_media_type(instance_qids: list[str]) -> str:
    for qid in instance_qids:
        if qid in _FILM_TYPES or qid in _DOC_TYPES:
            return "movie"
        if qid in _TV_TYPES:
            return "tv"
    return "movie" if instance_qids else "unknown"


def _merge_cjk_lines(text: str) -> str:
    """
    Joint les lignes consécutives composées uniquement de caractères CJK.
    Ex: "勝\n廣" → "勝廣"  (kanji sur deux lignes dans un OCR TikTok)
    """
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


async def _wd_get_entities(qids: list[str]) -> dict:
    if not qids:
        return {}
    params = {
        "action":    "wbgetentities",
        "ids":       "|".join(qids[:50]),
        "props":     "claims|labels|descriptions",
        "format":    "json",
        "languages": "en|fr|ja|ko|zh",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_WD_API, params=params,
                                    headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            return resp.json().get("entities", {})
    except Exception as e:
        print(f"⚠️ Wikidata getentities KO: {str(e)[:60]}", flush=True)
        return {}


# ════════════════════════════════════════════════════════════════
# PARSING D'ENTITÉ
# ════════════════════════════════════════════════════════════════

def _parse_entity(qid: str, entity: dict) -> Optional[dict]:
    claims = entity.get("claims", {})
    instance_qids = _claim_qids(claims, _P_INSTANCE_OF)
    media_type    = _resolve_media_type(instance_qids)

    tmdb_movie_id = _claim_value(claims, _P_TMDB_MOVIE)
    tmdb_tv_id    = _claim_value(claims, _P_TMDB_TV)
    imdb_id       = _claim_value(claims, _P_IMDB)

    if not tmdb_movie_id and not tmdb_tv_id and not imdb_id:
        return None

    if tmdb_tv_id and not tmdb_movie_id:
        media_type = "tv"
    elif tmdb_movie_id and not tmdb_tv_id and media_type == "unknown":
        media_type = "movie"

    tmdb_id = tmdb_movie_id or tmdb_tv_id
    year    = _claim_time(claims, _P_PUB_DATE)

    labels    = entity.get("labels", {})
    title_en  = labels.get("en", {}).get("value", "")
    title_fr  = labels.get("fr", {}).get("value", "")
    title_ja  = labels.get("ja", {}).get("value", "")
    title_ko  = labels.get("ko", {}).get("value", "")
    title_zh  = labels.get("zh", {}).get("value", "")
    title_orig = title_ja or title_ko or title_zh or title_en

    return {
        "wikidata_id": qid,
        "tmdb_id":     int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None,
        "imdb_id":     imdb_id,
        "media_type":  media_type,
        "year":        year,
        "title_en":    title_en,
        "title_fr":    title_fr,
        "title_orig":  title_orig,
    }


# ════════════════════════════════════════════════════════════════
# CONSTRUCTION DES REQUÊTES
# ════════════════════════════════════════════════════════════════

def _build_wikidata_queries(extraction: dict, ocr_text: str = "") -> list[tuple[str, str]]:
    """
    Construit les paires (query, lang) à envoyer à Wikidata.

    Priorité :
      1. Kanji/CJK fusionnés depuis l'OCR  ← le plus discriminant
      2. Titres certains Gemini
      3. Titres incertains Gemini
    """
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

    # ── 1. Séquences CJK dans l'OCR (après fusion des lignes) ────
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

    # ── 2. Titres certains Gemini ─────────────────────────────────
    for titre in titres_certains[:2]:
        if _has_cjk(titre):
            lang = "ja" if re.search(r'[぀-ゟ゠-ヿ]', titre) else "zh"
            queries.append((titre, lang))
        else:
            queries.append((titre, "en"))
            queries.append((titre, "fr"))

    # ── 3. Titres incertains Gemini ───────────────────────────────
    for titre in titres_incertains[:2]:
        if _has_cjk(titre):
            lang = "ja" if re.search(r'[぀-ゟ゠-ヿ]', titre) else "zh"
            queries.append((titre, lang))
        else:
            queries.append((titre, "en"))

    # Dédoublonnage + limite
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
# ENRICHISSEMENT TMDB / OMDB
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
            "_source":      "wikidata",
        }
    except Exception as e:
        print(f"⚠️ TMDB enrich KO (id={tmdb_id}): {str(e)[:60]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
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
      3. wbgetentities → TMDB/IMDB IDs
      4. Enrichir via TMDB (get_movie_details / get_tv_details)
      5. Retourner candidats normalisés pour rerank()
    """
    print("🌐 Wikidata search démarré...", flush=True)

    queries = _build_wikidata_queries(extraction, ocr_text)
    if not queries:
        print("🌐 Wikidata: aucune requête générée", flush=True)
        return []

    print(f"🌐 Wikidata queries ({len(queries)}): {queries}", flush=True)

    # ── Étape 1 : recherche → QIDs ───────────────────────────────
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

    # ── Étape 2 : claims → TMDB/IMDB IDs ────────────────────────
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
                f"imdb={result.get('imdb_id')} type={result.get('media_type')} "
                f"year={result.get('year')} "
                f"'{result.get('title_en') or result.get('title_orig')}'",
                flush=True
            )

    if not parsed:
        print("🌐 Wikidata: aucune entité avec IDs exploitables", flush=True)
        return []

    # ── Étape 3 : enrichissement TMDB ────────────────────────────
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

    # Fallback : entités sans TMDB ID → recherche par titre
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
    """
    Wikidata est déclenché quand :
      - Caractères CJK/coréens dans l'OCR ou les titres Gemini (peu importe le score)
      - OU score < 40 ET langue originale non-latine détectée
    """
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