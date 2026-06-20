"""
data/tmdb.py — Client TMDB avec stratégie multi-langue intelligente.
"""

import os
import asyncio
import httpx

API_KEY  = os.getenv("TMDB_API_KEY", "")
BASE_URL = "https://api.themoviedb.org/3"

_genre_cache: dict = {}

# ════════════════════════════════════════════════════════════════
# LANGUES TMDB
# ════════════════════════════════════════════════════════════════

_LANG_TO_LOCALE: dict[str, str] = {
    "af": "af-ZA", "ar": "ar-AE", "be": "be-BY", "bg": "bg-BG",
    "bn": "bn-BD", "ca": "ca-ES", "cs": "cs-CZ", "cy": "cy-GB",
    "da": "da-DK", "de": "de-DE", "el": "el-GR", "en": "en-US",
    "eo": "eo-EO", "es": "es-ES", "et": "et-EE", "eu": "eu-ES",
    "fa": "fa-IR", "fi": "fi-FI", "fr": "fr-FR", "ga": "ga-IE",
    "gl": "gl-ES", "gu": "gu-IN", "he": "he-IL", "hi": "hi-IN",
    "hr": "hr-HR", "hu": "hu-HU", "hy": "hy-AM", "id": "id-ID",
    "is": "is-IS", "it": "it-IT", "ja": "ja-JP", "ka": "ka-GE",
    "kk": "kk-KZ", "kn": "kn-IN", "ko": "ko-KR", "lt": "lt-LT",
    "lv": "lv-LV", "mk": "mk-MK", "ml": "ml-IN", "mr": "mr-IN",
    "ms": "ms-MY", "mt": "mt-MT", "nb": "nb-NO", "nl": "nl-NL",
    "no": "nb-NO", "pa": "pa-IN", "pl": "pl-PL", "pt": "pt-PT",
    "pt-br": "pt-BR", "ro": "ro-RO", "ru": "ru-RU", "sk": "sk-SK",
    "sl": "sl-SI", "sq": "sq-AL", "sr": "sr-RS", "sv": "sv-SE",
    "sw": "sw-KE", "ta": "ta-IN", "te": "te-IN", "th": "th-TH",
    "tl": "tl-PH", "tr": "tr-TR", "uk": "uk-UA", "ur": "ur-PK",
    "uz": "uz-UZ", "vi": "vi-VN", "zh": "zh-CN", "zh-tw": "zh-TW",
    "zu": "zu-ZA",
}

_ORIGINAL_LANG_PRIORITY = {"ja", "ko", "zh", "ar", "hi", "th", "ru", "he", "fa", "tr"}
FALLBACK_LOCALE = "en-US"


def _to_locale(lang_code: str) -> str:
    if not lang_code:
        return FALLBACK_LOCALE
    code = lang_code.lower().strip()
    if code in _LANG_TO_LOCALE:
        return _LANG_TO_LOCALE[code]
    base = code.split("-")[0]
    if base in _LANG_TO_LOCALE:
        return _LANG_TO_LOCALE[base]
    return FALLBACK_LOCALE


def _build_lang_priority(
    transcript_lang: str | None,
    browser_lang: str | None,
) -> list[str]:
    locales: list[str] = []

    def _add(lang: str | None) -> None:
        if not lang:
            return
        locale = _to_locale(lang)
        if locale not in locales:
            locales.append(locale)

    _add(transcript_lang)

    t = (transcript_lang or "").lower().split("-")[0]
    if t == "zh":
        _add("zh-TW")
    elif t == "pt":
        _add("pt-BR")

    _add(browser_lang)
    _add("en")

    return locales


# ════════════════════════════════════════════════════════════════
# REQUÊTES TMDB DE BASE
# ════════════════════════════════════════════════════════════════

async def _search_movies(query: str, locale: str) -> list:
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key":       API_KEY,
        "query":         query,
        "language":      locale,
        "page":          1,
        "include_adult": False,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            for r in results:
                r.setdefault("media_type", "movie")
                r["_search_locale"] = locale
            return results
    except Exception as e:
        print(f"⚠️ TMDB movie search [{locale}] KO: {e}", flush=True)
        return []


async def _search_tv(query: str, locale: str) -> list:
    url = f"{BASE_URL}/search/tv"
    params = {
        "api_key":       API_KEY,
        "query":         query,
        "language":      locale,
        "page":          1,
        "include_adult": False,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            for r in results:
                r.setdefault("media_type", "tv")
                r["_search_locale"] = locale
            return results
    except Exception as e:
        print(f"⚠️ TMDB tv search [{locale}] KO: {e}", flush=True)
        return []


# ════════════════════════════════════════════════════════════════
# RECHERCHE ÉPISODE → SÉRIE PARENTE
# ════════════════════════════════════════════════════════════════

def _similarity(a: str, b: str) -> float:
    """Similarité simple entre deux chaînes (ratio de caractères communs)."""
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    matches = sum(1 for c in shorter if c in longer)
    return matches / len(longer)


async def search_episode_parent_series(
    episode_title: str,
    lang: str = "en",
) -> list[dict]:
    """
    Cherche la série parente d'un titre d'épisode via TMDB.

    Stratégie :
      1. Recherche directe /search/tv avec le titre d'épisode
         → TMDB remonte souvent la série même avec un nom d'épisode célèbre
      2. Pour les 3 premières séries candidates, vérifie si un épisode matche
         en parcourant les saisons (max 5 saisons par série)

    Retourne les candidats triés : séries avec épisode matchant en premier.
    """
    results: list[dict] = []
    seen_ids: set = set()

    # ── Étape 1 : recherche directe comme série TV ────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/search/tv",
                params={
                    "api_key":       API_KEY,
                    "query":         episode_title,
                    "language":      lang,
                    "include_adult": False,
                },
            )
            resp.raise_for_status()
            for item in resp.json().get("results", [])[:5]:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    item["media_type"] = "tv"
                    results.append(item)
    except Exception as e:
        print(f"⚠️ search_episode_parent_series step1: {e}", flush=True)

    # ── Étape 2 : vérification épisodes ──────────────────────────
    episode_title_norm = episode_title.lower().strip()

    for series in results[:3]:
        series_id  = series.get("id")
        nb_seasons = series.get("number_of_seasons") or 1
        found      = False

        for season_num in range(1, min(nb_seasons + 1, 6)):
            if found:
                break
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    resp = await client.get(
                        f"{BASE_URL}/tv/{series_id}/season/{season_num}",
                        params={"api_key": API_KEY, "language": lang},
                    )
                    if resp.status_code != 200:
                        continue
                    for ep in resp.json().get("episodes", []):
                        ep_name = (ep.get("name") or "").lower().strip()
                        if (
                            episode_title_norm in ep_name
                            or ep_name in episode_title_norm
                            or _similarity(episode_title_norm, ep_name) > 0.8
                        ):
                            print(
                                f"📺 Épisode trouvé: '{ep.get('name')}' "
                                f"→ série '{series.get('name')}' "
                                f"S{season_num}E{ep.get('episode_number')}",
                                flush=True
                            )
                            found                    = True
                            series["_episode_match"] = True
                            series["_episode_name"]  = ep.get("name")
                            series["popularity"]     = (
                                series.get("popularity") or 0
                            ) + 100
                            break
            except Exception:
                continue

    results.sort(
        key=lambda x: (x.get("_episode_match", False), x.get("popularity", 0)),
        reverse=True,
    )
    return results[:5]


# ════════════════════════════════════════════════════════════════
# RECHERCHE MULTI-LANGUE (POINT D'ENTRÉE PRINCIPAL)
# ════════════════════════════════════════════════════════════════

async def search_multi_lang(
    query: str,
    transcript_lang: str | None = None,
    browser_lang: str | None = None,
    include_tv: bool = True,
) -> list:
    locales = _build_lang_priority(transcript_lang, browser_lang)
    print(
        f"🌍 TMDB multi-lang '{query}' — "
        f"transcript={transcript_lang}, browser={browser_lang} "
        f"→ locales={locales}",
        flush=True
    )

    tasks = [_search_movies(query, loc) for loc in locales]
    if include_tv:
        tasks += [_search_tv(query, loc) for loc in locales]

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen_ids: set = set()
    merged:   list = []

    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                merged.append(item)

    merged.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    print(
        f"✅ TMDB multi-lang → {len(merged)} candidats uniques "
        f"(avant: {sum(len(b) for b in batches if not isinstance(b, Exception))} bruts)",
        flush=True
    )

    return merged[:20]


# ════════════════════════════════════════════════════════════════
# COMPATIBILITÉ ASCENDANTE
# ════════════════════════════════════════════════════════════════

def _tmdb_lang(lang: str) -> str:
    return _to_locale(lang)


async def search_candidates(query: str, lang: str = "fr") -> list:
    return await _search_movies(query, _to_locale(lang))


async def search_tv_candidates(query: str, lang: str = "fr") -> list:
    return await _search_tv(query, _to_locale(lang))


# ════════════════════════════════════════════════════════════════
# DÉTAILS
# ════════════════════════════════════════════════════════════════

async def get_movie_details(movie_id: int, lang: str = "fr") -> dict:
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key":            API_KEY,
        "language":           _to_locale(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def get_tv_details(tv_id: int, lang: str = "fr") -> dict:
    url = f"{BASE_URL}/tv/{tv_id}"
    params = {
        "api_key":            API_KEY,
        "language":           _to_locale(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def get_genre_list(lang: str = "fr") -> list:
    locale = _to_locale(lang)
    if locale in _genre_cache:
        return _genre_cache[locale]
    url = f"{BASE_URL}/genre/movie/list"
    params = {"api_key": API_KEY, "language": locale}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        genres = resp.json().get("genres", [])
        _genre_cache[locale] = genres
        return genres


async def search_person(name: str, lang: str = "fr") -> dict | None:
    url = f"{BASE_URL}/search/person"
    params = {
        "api_key":  API_KEY,
        "query":    name,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None


async def get_person_credits(person_id: int, lang: str = "fr") -> list:
    url = f"{BASE_URL}/person/{person_id}/combined_credits"
    params = {
        "api_key":  API_KEY,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cast = data.get("cast", [])
        return sorted(cast, key=lambda x: x.get("popularity", 0), reverse=True)


async def discover_by_genre(
    genre_id: int,
    lang: str = "fr",
    page: int = 1,
    media_type: str = "movie",
) -> dict:
    endpoint = "discover/movie" if media_type != "tv" else "discover/tv"
    url = f"{BASE_URL}/{endpoint}"
    params = {
        "api_key":       API_KEY,
        "language":      _to_locale(lang),
        "with_genres":   str(genre_id),
        "page":          page,
        "sort_by":       "popularity.desc",
        "include_adult": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "results":       data.get("results", []),
            "page":          data.get("page", page),
            "total_pages":   data.get("total_pages", 1),
            "total_results": data.get("total_results", 0),
        }


async def get_trending(lang: str = "fr", media_type: str = "movie") -> list:
    url = f"{BASE_URL}/trending/{media_type}/week"
    params = {
        "api_key":  API_KEY,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])


async def discover_by_provider(provider_id: int, region: str, lang: str, page: int = 1):
   
    
    lang_map = {
        "fr": "fr-FR",
        "en": "en-US",
        "es": "es-ES",
        "de": "de-DE",
        "zh": "zh-CN"
    }

    params = {
        "api_key": API_KEY,
        "language": lang_map.get(lang, "fr-FR"),
        "with_watch_providers": provider_id,
        "watch_region": region,
        "sort_by": "popularity.desc",
        "page": page,
    }

    print(
        f"TMDB discover provider_id={provider_id} "
        f"region={region} "
        f"lang={lang} "
        f"page={page}",
        flush=True
    )

    print(params, flush=True)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{BASE_URL}/discover/movie",
            params=params
        )

        r.raise_for_status()
        data = r.json()
        print("📦 Réponse TMDB brute:", data)

    print(
        f"TMDB status={r.status_code} "
        f"results={len(data.get('results', []))} "
        f"total_pages={data.get('total_pages')}",
        flush=True
    )

    return {
        "results": data.get("results", []),
        "total_pages": min(data.get("total_pages", 1), 500),
        "page": data.get("page", 1),
        
    }

async def get_season_details(
    series_id: int,
    season_number: int,
    lang: str = "fr",
) -> dict:
    url = f"{BASE_URL}/tv/{series_id}/season/{season_number}"
    params = {
        "api_key":  API_KEY,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()