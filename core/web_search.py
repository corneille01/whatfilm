"""
core/web_search.py — Fallback web search pour les cas où TMDB échoue.

Déclenché quand :
  - score rerank < 50 après cascade TMDB
  - OU candidats vides
  - OU OCR contient des caractères CJK non exploités

Stratégie :
  1. Construire des requêtes ciblées depuis les indices Gemini + kanji OCR
  2. Chercher via DuckDuckGo (pas de clé API requise)
  3. Parser les snippets pour extraire des titres de films/séries
  4. Re-chercher ces titres sur TMDB pour obtenir des candidats normalisés
  5. Retourner une liste compatible avec rerank()

Limites volontaires :
  - Max 4 requêtes web par appel (éviter le rate-limit DDG)
  - Timeout 8s par requête
  - On ne fait jamais confiance à un titre web sans validation TMDB
"""

import re
import asyncio
from typing import Optional

# ════════════════════════════════════════════════════════════════
# DÉTECTION CJK / LANGUES ASIATIQUES
# ════════════════════════════════════════════════════════════════

_CJK_PATTERN  = re.compile(r'[一-鿿㐀-䶿\u3400-\u4DBF]')
_JP_PATTERN   = re.compile(r'[぀-ゟ゠-ヿ]')
_KO_PATTERN   = re.compile(r'[가-힯ᄀ-ᇿ]')


def _has_cjk(text: str) -> bool:
    return bool(_CJK_PATTERN.search(text) or _JP_PATTERN.search(text))


def _has_korean(text: str) -> bool:
    return bool(_KO_PATTERN.search(text))


def _extract_cjk(text: str) -> str:
    cjk_chars = re.findall(r'[一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ]+', text)
    return "".join(cjk_chars[:2])[:8]


def _extract_korean(text: str) -> str:
    ko_chars = re.findall(r'[가-힯ᄀ-ᇿ]+', text)
    return "".join(ko_chars[:2])[:8]


# ════════════════════════════════════════════════════════════════
# NETTOYAGE DES INDICES PARASITES
# ════════════════════════════════════════════════════════════════

# Termes méta qui n'ont aucune valeur discriminante pour une recherche film
_META_NOISE = {
    "concept vidéo", "concept video", "extrait", "clip", "bande-annonce",
    "trailer", "making of", "behind the scenes", "scène", "scene",
    "épave", "wreck", "ruins", "ruines", "débris",
}

def _clean_clue_for_search(clue: str) -> str:
    """
    Nettoie un indice visuel avant de l'utiliser dans une requête web.

    Exemples :
      'Titanic (épave) hélicoptère'  → 'Titanic hélicoptère'
      'arc (arme) uniforme scolaire' → 'arc uniforme scolaire'
      'concept vidéo montagne'       → 'montagne'
    """
    # 1. Supprimer les annotations entre parenthèses courtes (≤ 30 chars)
    cleaned = re.sub(r'\s*\([^)]{1,30}\)', '', clue).strip()

    # 2. Supprimer les termes méta parasites (insensible à la casse)
    for noise in _META_NOISE:
        cleaned = re.sub(
            rf'\b{re.escape(noise)}\b', '', cleaned, flags=re.IGNORECASE
        ).strip()

    # 3. Normaliser les espaces multiples
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _clean_clues(clues: list[str]) -> list[str]:
    """Nettoie une liste d'indices et supprime ceux devenus vides ou trop courts."""
    result = []
    seen: set = set()
    for c in clues:
        cleaned = _clean_clue_for_search(c)
        if cleaned and len(cleaned) > 2 and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            result.append(cleaned)
    return result


# ════════════════════════════════════════════════════════════════
# CONSTRUCTION DES REQUÊTES WEB
# ════════════════════════════════════════════════════════════════

def build_web_queries(extraction: dict, ocr_text: str = "") -> list[str]:
    """
    Construit des requêtes web ciblées depuis les indices Gemini + OCR.

    Fix v2 :
    - Nettoyage des indices parasites avant toute requête
      ('Titanic (épave) hélicoptère' → 'Titanic hélicoptère')
    - Diversification quand acteurs disponibles :
        requête A : acteur principal + genre (+ année si dispo)
        requête B : acteur1 + acteur2
        requête C : indices visuels nettoyés + movie
    - Ces requêtes acteur-first remontent en priorité 2b,
      avant les indices visuels (priorité 3)

    Priorité :
      0. Titres précis certains ou incertains précis
      1. CJK dans l'OCR (très discriminant)
      2. Titres incertains vagues + indices EN
      2b. Acteurs + genre / acteurs croisés  ← NOUVEAU
      3. Indices visuels nettoyés + "movie"
      4. Description courte → mots-clés EN
    """
    queries: list[str] = []

    titres_incertains = [
        str(t)[1:].strip()
        for t in extraction.get("titres_possibles", [])
        if str(t).startswith("?") and len(str(t)) > 2
    ]
    titres_certains = [
        str(t).strip()
        for t in extraction.get("titres_possibles", [])
        if not str(t).startswith("?") and len(str(t)) > 1
    ]
    acteurs = extraction.get("acteurs", []) or []
    indices = extraction.get("indices_visuels",   []) or []
    objets  = extraction.get("objets_importants", []) or []
    desc    = (extraction.get("description_courte", "") or "").strip()
    genre   = (extraction.get("genre_apparent",   "") or "").strip()
    annee   = str(extraction.get("annee_estimee") or "").strip()

    # Nettoyage des indices AVANT tout usage
    all_clues_raw   = [o for o in objets if o] + [i for i in indices if i]
    all_clues       = _clean_clues(all_clues_raw)

    genre_en = genre.replace("film-", "").replace("série", "series").strip()

    # ── Priorité 0 : titres précis ────────────────────────────────
    for titre in titres_certains[:2]:
        if not _has_cjk(titre) and not _has_korean(titre):
            queries.append(f'"{titre}" film site:imdb.com OR site:themoviedb.org')
        else:
            queries.append(f"{titre} film")

    for titre in titres_incertains[:2]:
        is_precise = (
            re.search(r'(?<=[a-z])[A-Z]', titre)
            or re.search(r'[,&:\d\-]', titre)
            or (len(titre.split()) >= 2
                and any(w[0].isupper() for w in titre.split()[1:] if w))
        )
        if is_precise:
            if not _has_cjk(titre) and not _has_korean(titre):
                queries.append(f'"{titre}" film')
            else:
                queries.append(f"{titre} film")

    # ── Priorité 1 : CJK dans l'OCR ──────────────────────────────
    ocr = (ocr_text or "").strip()
    cjk_from_ocr = _extract_cjk(ocr) if _has_cjk(ocr) else ""
    cjk_from_titles = ""
    for t in titres_incertains:
        if _has_cjk(t):
            cjk_from_titles = _extract_cjk(t)
            break

    cjk = cjk_from_ocr or cjk_from_titles
    if cjk:
        queries.append(f"{cjk} film")
        en_clues = _quick_translate(all_clues[:2])
        if en_clues:
            queries.append(f"{cjk} {' '.join(en_clues)} movie")

    # Coréen
    ko = _extract_korean(ocr) if _has_korean(ocr) else ""
    if not ko:
        for t in titres_incertains:
            if _has_korean(t):
                ko = _extract_korean(t)
                break
    if ko:
        queries.append(f"{ko} 영화")
        queries.append(f"{ko} film")

    # ── Priorité 2 : titres incertains vagues + indices EN ────────
    en_clues_all = _quick_translate(all_clues[:3])
    for titre in titres_incertains[:1]:
        if not re.search(r'(?<=[a-z])[A-Z]|[,&:\d\-]', titre):
            if en_clues_all:
                queries.append(f"{titre} {' '.join(en_clues_all[:2])} movie")
            else:
                queries.append(f"{titre} movie")

    # ── Priorité 2b : acteurs (NOUVEAU) ──────────────────────────
    # Quand les indices visuels sont peu fiables (score faible, confusion
    # entre objet reconnu et titre), les acteurs sont souvent le signal
    # le plus fiable. On génère jusqu'à 2 requêtes acteur-first.
    if acteurs:
        acteur_principal = acteurs[0]

        # Requête A : acteur + genre + année
        q_actor_genre = acteur_principal
        if genre_en and genre_en not in ("action", "drama", "thriller"):
            # genres trop génériques → inutiles dans une requête web
            q_actor_genre += f" {genre_en}"
        if annee:
            q_actor_genre += f" {annee}"
        q_actor_genre += " film"
        queries.append(q_actor_genre)

        # Requête B : croisement deux acteurs (très discriminant)
        if len(acteurs) >= 2:
            queries.append(f"{acteurs[0]} {acteurs[1]} film")

        # Requête C : acteur + indices nettoyés (si indices non vides après nettoyage)
        if all_clues:
            en_clues_actor = _quick_translate(all_clues[:2])
            if en_clues_actor:
                queries.append(f"{acteur_principal} {' '.join(en_clues_actor[:2])} movie")

    # ── Priorité 3 : indices visuels nettoyés + contexte asiatique ─
    if en_clues_all and len(en_clues_all) >= 2:
        asian_keyword = _detect_asian_keyword(all_clues, desc)
        base = " ".join(en_clues_all[:3])
        if asian_keyword:
            queries.append(f"{asian_keyword} movie {base}")
        else:
            queries.append(f"{base} movie")
        if annee:
            queries.append(f"{base} {annee} movie")

    # ── Priorité 4 : description courte → mots-clés EN ───────────
    if desc and len(desc) > 20:
        desc_en = _quick_translate_text(desc)
        if desc_en and len(desc_en) >= 2:
            queries.append(f"{' '.join(desc_en[:4])} movie")

    # ── Dédoublonnage + limite ────────────────────────────────────
    seen:   set  = set()
    result: list = []
    for q in queries:
        q = q.strip()
        if q and q not in seen and len(q) > 4:
            seen.add(q)
            result.append(q)
        if len(result) >= 5:
            break

    print(f"🌐 Web search queries ({len(result)}): {result}", flush=True)
    return result


# ════════════════════════════════════════════════════════════════
# TRADUCTION RAPIDE FR → EN (sans API)
# ════════════════════════════════════════════════════════════════

_QUICK_FR_EN: dict[str, str] = {
    "flèche": "arrow", "arc": "bow", "femme": "woman", "homme": "man",
    "épée": "sword", "katana": "katana", "kimono": "kimono",
    "samouraï": "samurai", "ninja": "ninja", "moine": "monk",
    "jardin japonais": "japanese garden", "temple": "temple",
    "château": "castle", "forêt": "forest", "combat": "fight",
    "arts martiaux": "martial arts", "geisha": "geisha",
    "tenue traditionnelle": "traditional costume",
    "vêtements traditionnels japonais": "japanese traditional clothing",
    "bannière rouge": "red banner", "petite amie": "girlfriend",
    "attrape": "catches", "tir": "shot", "guerrier": "warrior",
    "fantôme": "ghost", "magie": "magic", "dragon": "dragon",
    "école": "school", "uniforme": "uniform", "détective": "detective",
    "enquêteur": "detective", "gangster": "gangster", "yakuza": "yakuza",
    "ronin": "ronin", "shogun": "shogun",
    "robot": "robot", "humanoïde": "humanoid", "androïde": "android",
    "vaisseau": "spaceship", "espace": "space", "alien": "alien",
    "zombie": "zombie", "vampire": "vampire", "loup-garou": "werewolf",
    "super-héros": "superhero", "cape": "cape", "masque": "mask",
    "prison": "prison", "tribunal": "court", "avocat": "lawyer",
    "médecin": "doctor", "hôpital": "hospital", "ambulance": "ambulance",
    "policier": "police", "commissariat": "police station",
    "balançoire": "swing", "parc": "park", "enfant": "child",
    "fils": "son", "fille": "daughter", "mère": "mother", "père": "father",
    "hélicoptère": "helicopter", "avion": "aircraft", "bateau": "ship",
    "sous-marin": "submarine", "train": "train", "voiture": "car",
    "épave": "wreck", "ruines": "ruins", "désert": "desert",
    "montagne": "mountain", "océan": "ocean", "mer": "sea",
    "plage": "beach", "jungle": "jungle", "forêt tropicale": "rainforest",
    "ville": "city", "immeuble": "building", "gratte-ciel": "skyscraper",
    "laboratoire": "laboratory", "bunker": "bunker", "prison": "prison",
}

_ASIAN_SIGNALS_FR: dict[str, str] = {
    "japonais": "japanese", "coréen": "korean", "chinois": "chinese",
    "japonaise": "japanese", "coréenne": "korean", "thaï": "thai",
    "kimono": "japanese", "samouraï": "japanese", "geisha": "japanese",
    "katana": "japanese", "ninja": "japanese", "shogun": "japanese",
    "yakuza": "japanese", "ronin": "japanese",
    "hanbok": "korean", "k-drama": "korean",
    "qipao": "chinese", "wuxia": "chinese",
}


def _quick_translate(clues: list[str]) -> list[str]:
    result = []
    seen_en: set = set()
    for clue in clues:
        clue_lower = clue.lower().strip()
        matched = False
        for fr_key in sorted(_QUICK_FR_EN, key=len, reverse=True):
            if fr_key in clue_lower:
                en = _QUICK_FR_EN[fr_key]
                if en not in seen_en:
                    seen_en.add(en)
                    result.append(en)
                matched = True
                break
        if not matched and len(clue) > 3 and clue.isascii():
            if clue_lower not in seen_en:
                seen_en.add(clue_lower)
                result.append(clue)
    return result


def _quick_translate_text(text: str) -> list[str]:
    words: list[str] = []
    text_lower = text.lower()
    seen: set = set()
    for fr_key in sorted(_QUICK_FR_EN, key=len, reverse=True):
        if fr_key in text_lower:
            en = _QUICK_FR_EN[fr_key]
            if en not in seen:
                seen.add(en)
                words.append(en)
    return words


def _detect_asian_keyword(clues: list[str], desc: str) -> str:
    all_text = " ".join(clues + [desc]).lower()
    for signal, keyword in _ASIAN_SIGNALS_FR.items():
        if signal in all_text:
            return keyword
    return ""


# ════════════════════════════════════════════════════════════════
# EXTRACTION DE TITRES DEPUIS LES SNIPPETS WEB
# ════════════════════════════════════════════════════════════════

_TITLE_PATTERNS = [
    re.compile(r'^([^\(\[\|–—\-]{3,60})\s*[\(\[–—\-]\s*(\d{4})', re.MULTILINE),
    re.compile(r'^(.+?)\s*\((\d{4})\)\s*[-–—|]', re.MULTILINE),
    re.compile(r'([A-Z][^\.\!\?]{2,50})\s+is\s+a\s+(\d{4})\s+\w+\s+film', re.IGNORECASE),
    re.compile(r'([一-鿿㐀-䶿\u3400-\u4DBF぀-ゟ゠-ヿ가-힯]{2,20})'),
]

_NOISE_WORDS = {
    "imdb", "wikipedia", "themoviedb", "tmdb", "allocine", "letterboxd",
    "rotten", "tomatoes", "review", "trailer", "cast", "synopsis",
    "streaming", "watch", "online", "free", "download", "subtitle",
}


def _extract_titles_from_snippet(title: str, snippet: str) -> list[str]:
    found: list[str] = []
    text = f"{title}\n{snippet}"

    for pattern in _TITLE_PATTERNS:
        for m in pattern.finditer(text):
            candidate = m.group(1).strip()
            candidate = re.sub(r'\s+', ' ', candidate)
            if 2 <= len(candidate) <= 80:
                if not any(noise in candidate.lower() for noise in _NOISE_WORDS):
                    found.append(candidate)

    seen: set = set()
    result: list[str] = []
    for t in found:
        if t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result[:4]


# ════════════════════════════════════════════════════════════════
# RECHERCHE WEB (DuckDuckGo, sans clé API)
# ════════════════════════════════════════════════════════════════

async def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Recherche DuckDuckGo asynchrone via thread pool (DDGS est synchrone).
    Tente d'abord le nouveau package 'ddgs', puis l'ancien 'duckduckgo_search'.
    """
    def _sync_search():
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except ImportError:
            pass
        except Exception as e:
            print(f"⚠️ ddgs KO pour '{query[:40]}': {e}", flush=True)

        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            print(f"⚠️ duckduckgo_search KO pour '{query[:40]}': {e}", flush=True)

        return []

    loop = asyncio.get_event_loop()
    try:
        raw = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_search),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        print(f"⚠️ DDG timeout pour '{query[:40]}'", flush=True)
        return []

    return [
        {
            "title":   r.get("title", ""),
            "snippet": r.get("body", ""),
            "url":     r.get("href", ""),
        }
        for r in (raw or [])
    ]


# ════════════════════════════════════════════════════════════════
# PIPELINE COMPLET : web search → titres → TMDB
# ════════════════════════════════════════════════════════════════

async def web_search_fallback(
    extraction: dict,
    ocr_text: str = "",
    browser_lang: str = "fr",
    max_tmdb_candidates: int = 10,
) -> list[dict]:
    """
    Pipeline complet de fallback web search.

    1. Construit des requêtes depuis les indices Gemini + OCR CJK
    2. Cherche sur DuckDuckGo (max 4 requêtes)
    3. Extrait des titres candidats des snippets
    4. Valide chaque titre sur TMDB
    5. Retourne des candidats TMDB normalisés pour rerank()
    """
    print("🌐 Web search fallback démarré...", flush=True)

    queries = build_web_queries(extraction, ocr_text)
    if not queries:
        print("🌐 Aucune requête web générée", flush=True)
        return []

    # ── Étape 1 : recherches web (max 4, séquentielles) ──────────
    all_web_results: list[dict] = []
    for i, query in enumerate(queries[:4]):
        results = await _ddg_search(query, max_results=5)
        if results:
            print(f"  🔎 '{query[:50]}' → {len(results)} résultats web", flush=True)
            all_web_results.extend(results)
        if i < len(queries) - 1:
            await asyncio.sleep(0.5)

    if not all_web_results:
        print("🌐 Web search → aucun résultat", flush=True)
        return []

    # ── Étape 2 : extraction des titres candidats ─────────────────
    candidate_titles: list[str] = []
    seen_titles: set = set()

    for result in all_web_results:
        titles = _extract_titles_from_snippet(
            result.get("title", ""),
            result.get("snippet", ""),
        )
        for t in titles:
            if t.lower() not in seen_titles:
                seen_titles.add(t.lower())
                candidate_titles.append(t)

    # Séquences CJK brutes en priorité
    ocr_cjk = _extract_cjk((ocr_text or ""))
    if ocr_cjk and ocr_cjk not in seen_titles:
        candidate_titles.insert(0, ocr_cjk)

    for t in extraction.get("titres_possibles", []):
        t_clean = str(t).lstrip("?").strip()
        if t_clean and _has_cjk(t_clean) and t_clean not in seen_titles:
            candidate_titles.insert(0, t_clean)

    # Titres précis Gemini directement
    for t in extraction.get("titres_possibles", []):
        t_clean = str(t).lstrip("?").strip()
        if not t_clean or _has_cjk(t_clean):
            continue
        is_precise = (
            re.search(r'(?<=[a-z])[A-Z]', t_clean)
            or re.search(r'[,&:\d\-]', t_clean)
            or (len(t_clean.split()) >= 2
                and any(w[0].isupper() for w in t_clean.split()[1:] if w))
        )
        if is_precise and t_clean.lower() not in seen_titles:
            seen_titles.add(t_clean.lower())
            candidate_titles.append(t_clean)

    # ── Étape 2b : acteurs comme titres de recherche TMDB directs ─
    # Quand les snippets web ne donnent rien d'exploitable,
    # rechercher les acteurs directement sur TMDB comme fallback ultime.
    acteurs = extraction.get("acteurs", []) or []
    if acteurs and not candidate_titles:
        print(
            f"🌐 Aucun titre extrait des snippets → recherche TMDB directe "
            f"par acteurs: {acteurs[:2]}",
            flush=True
        )
        # On injecte les acteurs comme "titres candidats" — search_multi_lang
        # les trouvera via /search/person et retournera leurs films
        for acteur in acteurs[:2]:
            if acteur.lower() not in seen_titles:
                seen_titles.add(acteur.lower())
                candidate_titles.append(acteur)

    if not candidate_titles:
        print("🌐 Web search → aucun titre extrait des snippets", flush=True)
        return []

    print(f"🌐 Titres candidats extraits: {candidate_titles[:6]}", flush=True)

    # ── Étape 3 : validation TMDB pour chaque titre trouvé ────────
    from data.tmdb import search_multi_lang

    tmdb_candidates: list[dict] = []
    seen_ids: set = set()

    transcript_lang = extraction.get("langue_originale") or None
    if not transcript_lang:
        combined = (ocr_text or "") + " ".join(
            str(t) for t in extraction.get("titres_possibles", [])
        )
        if _has_cjk(combined) and _JP_PATTERN.search(combined):
            transcript_lang = "ja"
        elif _has_cjk(combined):
            transcript_lang = "zh"
        elif _has_korean(combined):
            transcript_lang = "ko"

    for titre in candidate_titles[:8]:
        try:
            results = await search_multi_lang(
                titre,
                transcript_lang=transcript_lang,
                browser_lang=browser_lang,
            )
            for item in results[:3]:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    item["_web_search_origin"] = titre
                    tmdb_candidates.append(item)
        except Exception as e:
            print(f"⚠️ TMDB validation KO pour '{titre[:30]}': {e}", flush=True)

        if len(tmdb_candidates) >= max_tmdb_candidates:
            break

    tmdb_candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    print(
        f"✅ Web search fallback → {len(tmdb_candidates)} candidats TMDB "
        f"(depuis {len(candidate_titles)} titres web)",
        flush=True
    )
    return tmdb_candidates[:max_tmdb_candidates]


# ════════════════════════════════════════════════════════════════
# HELPER : doit-on déclencher le fallback ?
# ════════════════════════════════════════════════════════════════

def should_trigger_web_fallback(
    score: int,
    candidates: list,
    extraction: dict,
    ocr_text: str = "",
) -> bool:
    if not candidates:
        print("🌐 Trigger web fallback: aucun candidat TMDB", flush=True)
        return True

    if score < 50:
        print(f"🌐 Trigger web fallback: score faible ({score})", flush=True)
        return True

    combined_cjk = (ocr_text or "") + " ".join(
        str(t) for t in extraction.get("titres_possibles", [])
    )
    if _has_cjk(combined_cjk) or _has_korean(combined_cjk):
        print("🌐 Trigger web fallback: caractères CJK/coréens détectés", flush=True)
        return True

    return False