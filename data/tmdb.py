"""
data/tmdb.py — Client TMDB avec stratégie multi-langue intelligente.

Stratégie de recherche par langue :
  1. Langue de la transcription  (langue du film lui-même)
  2. Langue du navigateur        (langue de l'utilisateur pour les titres localisés)
  3. Anglais                     (fallback universel TMDB)
  → Les doublons sont filtrés, les résultats fusionnés par popularité.

Langues supportées : tous les codes ISO 639-1 reconnus par TMDB.
"""

import os
import asyncio
import httpx

API_KEY  = os.getenv("TMDB_API_KEY", "")
BASE_URL = "https://api.themoviedb.org/3"

_genre_cache: dict = {}

# ════════════════════════════════════════════════════════════════
# LANGUES TMDB
# Tous les codes ISO 639-1 supportés par TMDB.
# Source : https://developer.themoviedb.org/docs/languages
# ════════════════════════════════════════════════════════════════

# Mapping code court → locale TMDB complète (xx-XX)
# Utilisé pour les appels "language=" qui influencent les titres retournés.
_LANG_TO_LOCALE: dict[str, str] = {
    "af": "af-ZA",  # Afrikaans
    "ar": "ar-AE",  # Arabe
    "be": "be-BY",  # Biélorusse
    "bg": "bg-BG",  # Bulgare
    "bn": "bn-BD",  # Bengali
    "ca": "ca-ES",  # Catalan
    "cs": "cs-CZ",  # Tchèque
    "cy": "cy-GB",  # Gallois
    "da": "da-DK",  # Danois
    "de": "de-DE",  # Allemand
    "el": "el-GR",  # Grec
    "en": "en-US",  # Anglais
    "eo": "eo-EO",  # Espéranto
    "es": "es-ES",  # Espagnol
    "et": "et-EE",  # Estonien
    "eu": "eu-ES",  # Basque
    "fa": "fa-IR",  # Persan
    "fi": "fi-FI",  # Finnois
    "fr": "fr-FR",  # Français
    "ga": "ga-IE",  # Irlandais
    "gl": "gl-ES",  # Galicien
    "gu": "gu-IN",  # Gujarati
    "he": "he-IL",  # Hébreu
    "hi": "hi-IN",  # Hindi
    "hr": "hr-HR",  # Croate
    "hu": "hu-HU",  # Hongrois
    "hy": "hy-AM",  # Arménien
    "id": "id-ID",  # Indonésien
    "is": "is-IS",  # Islandais
    "it": "it-IT",  # Italien
    "ja": "ja-JP",  # Japonais
    "ka": "ka-GE",  # Géorgien
    "kk": "kk-KZ",  # Kazakh
    "kn": "kn-IN",  # Kannada
    "ko": "ko-KR",  # Coréen
    "lt": "lt-LT",  # Lituanien
    "lv": "lv-LV",  # Letton
    "mk": "mk-MK",  # Macédonien
    "ml": "ml-IN",  # Malayalam
    "mr": "mr-IN",  # Marathi
    "ms": "ms-MY",  # Malais
    "mt": "mt-MT",  # Maltais
    "nb": "nb-NO",  # Norvégien Bokmål
    "nl": "nl-NL",  # Néerlandais
    "no": "nb-NO",  # Norvégien (alias)
    "pa": "pa-IN",  # Pendjabi
    "pl": "pl-PL",  # Polonais
    "pt": "pt-PT",  # Portugais
    "pt-br": "pt-BR",  # Portugais brésilien
    "ro": "ro-RO",  # Roumain
    "ru": "ru-RU",  # Russe
    "sk": "sk-SK",  # Slovaque
    "sl": "sl-SI",  # Slovène
    "sq": "sq-AL",  # Albanais
    "sr": "sr-RS",  # Serbe
    "sv": "sv-SE",  # Suédois
    "sw": "sw-KE",  # Swahili
    "ta": "ta-IN",  # Tamoul
    "te": "te-IN",  # Télougou
    "th": "th-TH",  # Thaï
    "tl": "tl-PH",  # Filipino
    "tr": "tr-TR",  # Turc
    "uk": "uk-UA",  # Ukrainien
    "ur": "ur-PK",  # Ourdou
    "uz": "uz-UZ",  # Ouzbek
    "vi": "vi-VN",  # Vietnamien
    "zh": "zh-CN",  # Chinois simplifié
    "zh-tw": "zh-TW",  # Chinois traditionnel
    "zu": "zu-ZA",  # Zoulou
}

# Langues dont les films ont souvent des titres originaux non traduits dans d'autres langues.
# Pour ces langues, on cherche TOUJOURS en original + anglais même si la langue nav correspond.
_ORIGINAL_LANG_PRIORITY = {"ja", "ko", "zh", "ar", "hi", "th", "ru", "he", "fa", "tr"}

FALLBACK_LOCALE = "en-US"


def _to_locale(lang_code: str) -> str:
    """
    Convertit un code langue ISO 639-1 (éventuellement avec région) en locale TMDB.
    Exemples : "fr" → "fr-FR", "pt-BR" → "pt-BR", "zh-tw" → "zh-TW", "xyz" → "en-US"
    """
    if not lang_code:
        return FALLBACK_LOCALE
    code = lang_code.lower().strip()
    # Cas exact
    if code in _LANG_TO_LOCALE:
        return _LANG_TO_LOCALE[code]
    # Cas avec région (ex: "fr-be" → essayer "fr")
    base = code.split("-")[0]
    if base in _LANG_TO_LOCALE:
        return _LANG_TO_LOCALE[base]
    return FALLBACK_LOCALE


def _build_lang_priority(
    transcript_lang: str | None,
    browser_lang: str | None,
) -> list[str]:
    """
    Construit la liste ordonnée de locales TMDB à interroger.

    Règles :
      1. Langue de la transcription (langue du film)  → toujours en premier
      2. Langue du navigateur (affichage utilisateur) → si différente de 1
      3. Anglais                                      → toujours en dernier (fallback)

    Si la langue originale fait partie de _ORIGINAL_LANG_PRIORITY (ja, ko, zh...),
    on ajoute aussi zh-TW ou ja-JP selon le cas pour couvrir les variantes.

    Résultat : liste de locales sans doublons, max 4 éléments.
    """
    locales: list[str] = []

    def _add(lang: str | None) -> None:
        if not lang:
            return
        locale = _to_locale(lang)
        if locale not in locales:
            locales.append(locale)

    # 1. Transcription
    _add(transcript_lang)

    # Variantes pour langues à priorité originale
    t = (transcript_lang or "").lower().split("-")[0]
    if t == "zh":
        _add("zh-TW")  # couvrir les deux formes
    elif t == "pt":
        _add("pt-BR")

    # 2. Navigateur
    _add(browser_lang)

    # 3. Anglais (toujours)
    _add("en")

    return locales


# ════════════════════════════════════════════════════════════════
# REQUÊTES TMDB DE BASE
# ════════════════════════════════════════════════════════════════

async def _search_movies(query: str, locale: str) -> list:
    """Recherche films TMDB dans une locale donnée."""
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key": API_KEY,
        "query": query,
        "language": locale,
        "page": 1,
        "include_adult": False,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            # Injecter media_type et locale source pour traçabilité
            for r in results:
                r.setdefault("media_type", "movie")
                r["_search_locale"] = locale
            return results
    except Exception as e:
        print(f"⚠️ TMDB movie search [{locale}] KO: {e}", flush=True)
        return []


async def _search_tv(query: str, locale: str) -> list:
    """Recherche séries TV TMDB dans une locale donnée."""
    url = f"{BASE_URL}/search/tv"
    params = {
        "api_key": API_KEY,
        "query": query,
        "language": locale,
        "page": 1,
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
# RECHERCHE MULTI-LANGUE (POINT D'ENTRÉE PRINCIPAL)
# ════════════════════════════════════════════════════════════════

async def search_multi_lang(
    query: str,
    transcript_lang: str | None = None,
    browser_lang: str | None = None,
    include_tv: bool = True,
) -> list:
    """
    Recherche TMDB multi-langue intelligente.

    Args:
        query:           Requête de recherche.
        transcript_lang: Code ISO 639-1 de la langue de la transcription
                         (ex: "fr", "ja", "ko"). Priorité maximale.
        browser_lang:    Code ISO 639-1 de la langue du navigateur de l'utilisateur
                         (ex: "fr", "de", "ar"). Priorité secondaire.
        include_tv:      Inclure les séries TV dans les résultats.

    Returns:
        Liste fusionnée, dédoublonnée, triée par popularité. Max 20 items.
    """
    locales = _build_lang_priority(transcript_lang, browser_lang)
    print(
        f"🌍 TMDB multi-lang '{query}' — "
        f"transcript={transcript_lang}, browser={browser_lang} "
        f"→ locales={locales}",
        flush=True
    )

    # Lancer toutes les requêtes en parallèle
    tasks = [_search_movies(query, loc) for loc in locales]
    if include_tv:
        tasks += [_search_tv(query, loc) for loc in locales]

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    # Fusion et dédoublonnage par id TMDB
    # On garde le premier résultat rencontré (priorité = ordre des locales)
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

    # Trier par popularité décroissante
    merged.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    print(
        f"✅ TMDB multi-lang → {len(merged)} candidats uniques "
        f"(avant: {sum(len(b) for b in batches if not isinstance(b, Exception))} bruts)",
        flush=True
    )

    return merged[:20]


# ════════════════════════════════════════════════════════════════
# COMPATIBILITÉ ASCENDANTE
# Les fonctions originales restent disponibles pour ne pas casser l'existant.
# ════════════════════════════════════════════════════════════════

def _tmdb_lang(lang: str) -> str:
    """Compatibilité : convertit un code court en locale TMDB."""
    return _to_locale(lang)


async def search_candidates(query: str, lang: str = "fr") -> list:
    """Recherche films uniquement (compatibilité ascendante)."""
    return await _search_movies(query, _to_locale(lang))


async def search_tv_candidates(query: str, lang: str = "fr") -> list:
    """Recherche séries TV uniquement (compatibilité ascendante)."""
    return await _search_tv(query, _to_locale(lang))


# ════════════════════════════════════════════════════════════════
# DÉTAILS
# ════════════════════════════════════════════════════════════════

async def get_movie_details(movie_id: int, lang: str = "fr") -> dict:
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": API_KEY,
        "language": _to_locale(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def get_tv_details(tv_id: int, lang: str = "fr") -> dict:
    url = f"{BASE_URL}/tv/{tv_id}"
    params = {
        "api_key": API_KEY,
        "language": _to_locale(lang),
        "append_to_response": "credits,videos,similar,recommendations,watch/providers",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def get_genre_list(lang: str = "fr") -> list:
    """Retourne la liste des genres de films (avec cache)."""
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
        "api_key": API_KEY,
        "query": name,
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
        "api_key": API_KEY,
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
        "api_key": API_KEY,
        "language": _to_locale(lang),
        "with_genres": str(genre_id),
        "page": page,
        "sort_by": "popularity.desc",
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
        "api_key": API_KEY,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])


async def get_season_details(
    series_id: int,
    season_number: int,
    lang: str = "fr",
) -> dict:
    url = f"{BASE_URL}/tv/{series_id}/season/{season_number}"
    params = {
        "api_key": API_KEY,
        "language": _to_locale(lang),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()