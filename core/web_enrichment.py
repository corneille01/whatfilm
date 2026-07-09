"""
core/web_enrichment.py — Web clue enrichment léger avant cascade TMDB.

Objectif :
- Utiliser le web pour corroborer/enrichir les indices extraits par Gemini/Qwen.
- Ne remplace PAS TMDB.
- Ne remplace PAS le web fallback complet.
- Ajoute seulement quelques titres/années possibles dans extraction_json.
"""

import os
import re
import html
from collections import Counter
from urllib.parse import urlparse, parse_qs, unquote

import httpx


WEB_LIGHT_ENABLED = os.environ.get("WEB_LIGHT_ENABLED", "true").lower() == "true"
WEB_LIGHT_MAX_QUERIES = int(os.environ.get("WEB_LIGHT_MAX_QUERIES", "3"))
WEB_LIGHT_MAX_RESULTS_PER_QUERY = int(os.environ.get("WEB_LIGHT_MAX_RESULTS_PER_QUERY", "3"))

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-3][0-9])\b")

BAD_WEB_TITLES = {
    "film",
    "movie",
    "movies",
    "review",
    "reviews",
    "trailer",
    "official trailer",
    "watch",
    "streaming",
    "stream",
    "配信",
    "動画",
    "映画情報",
    "レビュー",
    "評価",
    "あらすじ",
    "senscritique",
    "allociné",
    "imdb",
    "wikipedia",
    "youtube",
    "prime video",
    "netflix",
}


def _norm(text: str) -> str:
    text = str(text or "").lower().strip()
    text = text.lstrip("?")
    text = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", "", text)
    return text


def _strip_uncertain(title: str) -> str:
    return str(title or "").strip().lstrip("?").strip()


def _plain_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_web_title(title: str) -> str:
    title = _plain_html(title)

    # Supprime les suffixes de sites fréquents.
    title = re.split(
        r"\s[-|–—]\s(?:IMDb|Wikipedia|TMDB|The Movie Database|Letterboxd|"
        r"Rotten Tomatoes|YouTube|AsianWiki|MyDramaList|Fandom|Allociné|"
        r"SensCritique|Prime Video|Netflix|JustWatch)",
        title,
        flags=re.IGNORECASE,
    )[0].strip()

    # Ex: "Teketeke (2009 film)" → "Teketeke"
    title = re.sub(
        r"\s*\((?:19[0-9]{2}|20[0-3][0-9]|film|movie|tv series|anime|"
        r"japanese film|horror film|short film).*?\)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    # Ex: "Teke Teke movie review" → "Teke Teke"
    title = re.sub(
        r"\b(movie|film|review|trailer|streaming|watch online)\b.*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    return title.strip(" -–—|:•\t\n\r")


def _looks_like_title(title: str) -> bool:
    title = _clean_web_title(title)
    if not title:
        return False

    low = title.lower().strip()
    if low in BAD_WEB_TITLES:
        return False

    if len(title) < 2 or len(title) > 70:
        return False

    # Les titres CJK peuvent être courts.
    if CJK_RE.search(title):
        return True

    words = title.split()
    if len(words) > 8:
        return False

    # Évite les morceaux trop génériques.
    generic = {"official", "full", "hd", "video", "clip", "scene", "ending"}
    if all(w.lower() in generic for w in words):
        return False

    return True


def _extract_cjk_terms(text: str, limit: int = 2) -> list[str]:
    terms = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]{2,20}", text or "")
    seen = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _extract_quote(transcript: str) -> str:
    """
    Extrait une réplique assez longue pour être cherchée.
    On évite de chercher toute la transcription.
    """
    transcript = re.sub(r"\s+", " ", transcript or "").strip()
    if len(transcript) < 80:
        return ""

    sentences = re.split(r"[.!?。！？\n]+", transcript)
    candidates = []

    for s in sentences:
        s = s.strip()
        words = s.split()
        if 7 <= len(words) <= 16 and len(s) <= 120:
            candidates.append(s)

    if candidates:
        return candidates[0]

    words = transcript.split()
    if len(words) >= 9:
        return " ".join(words[:12])

    return ""


def should_trigger_light_web_enrichment(
    extraction: dict,
    ocr_text: str = "",
    transcript: str = "",
) -> bool:
    if not WEB_LIGHT_ENABLED:
        return False

    extraction = extraction or {}

    titres = extraction.get("titres_possibles", []) or []
    acteurs = extraction.get("acteurs", []) or []
    personnages = extraction.get("personnages", []) or []
    description = extraction.get("description_courte", "") or ""
    indices = extraction.get("indices_visuels", []) or []
    objets = extraction.get("objets_importants", []) or []

    joined = " ".join(
        [str(x) for x in titres + acteurs + personnages + indices + objets]
        + [description, ocr_text or "", transcript or ""]
    )

    has_title = bool(titres)
    has_uncertain_title = any(str(t).strip().startswith("?") for t in titres)
    has_cjk = bool(CJK_RE.search(joined))
    has_long_quote = len(transcript or "") >= 100
    has_named_clue = bool(acteurs or personnages)
    has_visual_but_no_title = bool((indices or objets or description) and not titres)

    # Si ton extraction a un score dans le futur, on l'utilise aussi.
    ai_score = extraction.get("confidence") or extraction.get("score") or 0
    has_low_ai_score = isinstance(ai_score, (int, float)) and 0 < ai_score < 70

    return any([
        has_title,
        has_uncertain_title,
        has_cjk,
        has_long_quote,
        has_named_clue,
        has_visual_but_no_title,
        has_low_ai_score,
    ])


def _build_light_queries(
    extraction: dict,
    ocr_text: str = "",
    transcript: str = "",
    max_queries: int = WEB_LIGHT_MAX_QUERIES,
) -> list[str]:
    extraction = extraction or {}

    titres = [_strip_uncertain(t) for t in extraction.get("titres_possibles", []) or [] if str(t).strip()]
    acteurs = [str(a).strip() for a in extraction.get("acteurs", []) or [] if str(a).strip()]
    personnages = [str(p).strip() for p in extraction.get("personnages", []) or [] if str(p).strip()]
    genre = (extraction.get("genre_apparent") or "").replace("film-", "").replace("série", "series").strip()
    annee = str(extraction.get("annee_estimee") or "").strip()

    queries = []

    # 1) Titre probable : signal le plus fort.
    for title in titres[:2]:
        if not title:
            continue
        if CJK_RE.search(title):
            queries.append(f'"{title}" film')
        elif annee:
            queries.append(f'"{title}" {annee} movie')
        else:
            queries.append(f'"{title}" movie')

    # 2) OCR CJK : souvent titre original, générique, bannière.
    for term in _extract_cjk_terms((ocr_text or "") + " " + " ".join(titres), limit=2):
        queries.append(f'"{term}" film')

    # 3) Acteur/personnage + genre.
    if acteurs and not titres:
        q = f'"{acteurs[0]}" {genre or "movie"}'
        if annee:
            q += f" {annee}"
        queries.append(q)

    if personnages and not titres:
        queries.append(f'"{personnages[0]}" {genre or "movie"}')

    # 4) Réplique longue.
    quote = _extract_quote(transcript)
    if quote:
        queries.append(f'"{quote}" movie')

    # Dédoublonnage + limite.
    seen = set()
    out = []
    for q in queries:
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_queries:
            break

    return out


def _decode_ddg_url(url: str) -> str:
    try:
        parsed = urlparse(html.unescape(url))
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    except Exception:
        pass
    return html.unescape(url)


async def _ddg_search(query: str, max_results: int = WEB_LIGHT_MAX_RESULTS_PER_QUERY) -> list[dict]:
    """
    Recherche légère sans API key.
    Si DDG timeout ou change son HTML, on retourne [] sans casser Pelify.
    """
    url = "https://duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PelifyBot/1.0; +https://pelify.app)"
    }

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url, params={"q": query, "kl": "wt-wt"})
            resp.raise_for_status()

        page = resp.text

        links = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            page,
            flags=re.IGNORECASE | re.DOTALL,
        )

        snippets = re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|'
            r'<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
            page,
            flags=re.IGNORECASE | re.DOTALL,
        )

        clean_snippets = []
        for s1, s2 in snippets:
            clean_snippets.append(_plain_html(s1 or s2))

        results = []
        for i, (href, title_html) in enumerate(links[:max_results]):
            title = _plain_html(title_html)
            results.append({
                "title": title,
                "url": _decode_ddg_url(href),
                "snippet": clean_snippets[i] if i < len(clean_snippets) else "",
            })

        return results

    except Exception as e:
        print(f"⚠️ Web light timeout/KO pour {query!r}: {str(e)[:100]}", flush=True)
        return []


def _extract_titles_from_result(result: dict) -> list[str]:
    titles = []

    raw_title = result.get("title", "") or ""
    cleaned = _clean_web_title(raw_title)
    if _looks_like_title(cleaned):
        titles.append(cleaned)

    text = f"{raw_title} {result.get('snippet', '')}"

    # Titres entre guillemets.
    for m in re.finditer(r'[«"“](.{2,70}?)[»"”]', text):
        candidate = _clean_web_title(m.group(1))
        if _looks_like_title(candidate):
            titles.append(candidate)

    # Titre CJK dans snippet/titre.
    for term in _extract_cjk_terms(text, limit=3):
        if _looks_like_title(term):
            titles.append(term)

    # Dédoublonnage local.
    seen = set()
    out = []
    for t in titles:
        n = _norm(t)
        if n and n not in seen:
            seen.add(n)
            out.append(t)

    return out


def _append_web_titles_to_extraction(extraction: dict, web_titles: list[str]) -> dict:
    extraction = dict(extraction or {})
    existing = list(extraction.get("titres_possibles", []) or [])
    existing_norms = {_norm(t) for t in existing}

    added = []
    for title in web_titles:
        title = _clean_web_title(title)
        n = _norm(title)
        if not n or n in existing_norms:
            continue

        # On garde le préfixe "?" pour éviter de transformer un indice web en certitude absolue.
        existing.append(f"?{title}")
        existing_norms.add(n)
        added.append(title)

    extraction["titres_possibles"] = existing

    if added:
        print(f"🌐 Web light → titres ajoutés: {added[:5]}", flush=True)

    return extraction


async def light_web_enrich_extraction(
    extraction: dict,
    ocr_text: str = "",
    transcript: str = "",
    browser_lang: str = "fr",
) -> dict:
    """
    Enrichit extraction_json AVANT run_cascade_search.
    Retourne toujours une extraction, même si le web échoue.
    """
    extraction = dict(extraction or {})

    if not should_trigger_light_web_enrichment(extraction, ocr_text, transcript):
        return extraction

    queries = _build_light_queries(extraction, ocr_text, transcript)
    if not queries:
        return extraction

    print(f"🌐 Web light queries ({len(queries)}): {queries}", flush=True)

    all_results = []
    for query in queries:
        results = await _ddg_search(query, max_results=WEB_LIGHT_MAX_RESULTS_PER_QUERY)
        print(f"  🔎 Web light {query!r} → {len(results)} résultats", flush=True)
        all_results.extend(results)

    if not all_results:
        return extraction

    title_counts = Counter()
    years = []

    for result in all_results:
        for title in _extract_titles_from_result(result):
            title_counts[title] += 1

        text = f"{result.get('title', '')} {result.get('snippet', '')}"
        years.extend(YEAR_RE.findall(text))

    # On garde peu de titres pour ne pas polluer TMDB.
    web_titles = [title for title, _count in title_counts.most_common(5)]

    if web_titles:
        extraction = _append_web_titles_to_extraction(extraction, web_titles)

    # Si l'année revient souvent et que Gemini/Qwen n'a rien donné.
    if not extraction.get("annee_estimee") and years:
        year_counts = Counter(years)
        best_year, count = year_counts.most_common(1)[0]
        if count >= 2:
            extraction["annee_estimee"] = int(best_year)
            print(f"🌐 Web light → année ajoutée: {best_year}", flush=True)

    extraction["web_light"] = {
        "queries": queries,
        "titles": web_titles[:5],
        "results_count": len(all_results),
        "years": list(dict.fromkeys(years))[:5],
    }

    return extraction


def result_supported_by_web_light(result: dict, extraction: dict) -> bool:
    """
    Sert au score composite : le résultat choisi est-il corroboré par les titres web légers ?
    """
    if not result or not extraction:
        return False

    web = extraction.get("web_light") or {}
    web_titles = web.get("titles") or []
    if not web_titles:
        return False

    chosen = result.get("meilleur_titre") or result.get("title") or result.get("name") or ""
    chosen_norm = _norm(chosen)

    if not chosen_norm:
        return False

    for title in web_titles:
        if _norm(title) == chosen_norm:
            return True

    # Tolérance : Teke Teke vs Teketeke.
    for title in web_titles:
        tnorm = _norm(title)
        if tnorm and (tnorm in chosen_norm or chosen_norm in tnorm):
            return True

    return False