"""
core/quote_search.py — Ancrage par réplique exacte (dialogue anchoring).

Objectif : utiliser le transcript (Whisper) comme signal de vérification
externe, indépendant du LLM. Une réplique de 5-14 mots est quasi unique
sur le web ; si elle apparaît verbatim associée à un titre de film/série,
c'est un signal beaucoup plus fiable qu'un score auto-déclaré par un LLM
(qui peut halluciner avec assurance).

Stratégie :
  1. Extraire 2-3 répliques "citables" du transcript (assez longues,
     peu génériques, sans bruit de transcription).
  2. Chercher chaque réplique entre guillemets sur le web (DuckDuckGo).
  3. Extraire les titres mentionnés dans les résultats (réutilise la
     logique déjà présente dans core/web_search.py).
  4. Valider ces titres sur TMDB.
  5. Retourner une liste de candidats corroborés, exploitable soit comme
     nouveaux candidats pour rerank(), soit comme signal de boost si un
     candidat déjà trouvé par un autre canal (cascade, acteurs) coïncide.

Ce module ne remplace jamais le rerank existant : il fournit un signal
de corroboration supplémentaire, indépendant du jugement du LLM.
"""

import re
import asyncio
from typing import Optional

from core.web_search import _ddg_search, _extract_titles_from_snippet


# ════════════════════════════════════════════════════════════════
# EXTRACTION DES RÉPLIQUES CITABLES
# ════════════════════════════════════════════════════════════════

# Expressions trop génériques pour être discriminantes même à 8+ mots
_GENERIC_FILLERS = {
    "je ne sais pas", "je sais pas", "c'est vrai", "tu sais",
    "ecoute moi", "écoute moi", "attends attends", "oh mon dieu",
    "qu'est-ce que tu fais", "qu'est ce que tu fais",
    "i don't know", "you know what", "come on", "let's go",
    "what are you doing", "oh my god", "i can't believe",
    "what's going on", "wait wait wait",
}

_MIN_QUOTE_WORDS = 5
_MAX_QUOTE_WORDS = 14
_MAX_QUOTES      = 3


def _split_sentences(transcript: str) -> list[str]:
    """Découpe le transcript en phrases exploitables."""
    text = re.sub(r'\s+', ' ', transcript or "").strip()
    raw = re.split(r'(?<=[.!?…])\s+', text)
    return [s.strip() for s in raw if s.strip()]


def _is_quotable(sentence: str) -> bool:
    words = sentence.split()
    n = len(words)
    if n < _MIN_QUOTE_WORDS or n > _MAX_QUOTE_WORDS:
        return False

    lower = sentence.lower()
    if lower in _GENERIC_FILLERS:
        return False

    # Phrase dominée par du remplissage générique → peu discriminante
    filler_word_count = 0
    for filler in _GENERIC_FILLERS:
        if filler in lower:
            filler_word_count += len(filler.split())
    if filler_word_count / n > 0.5:
        return False

    # Écarte le bruit de transcription (timestamps, texte non-alphabétique)
    alpha_ratio = sum(c.isalpha() for c in sentence) / max(len(sentence), 1)
    if alpha_ratio < 0.6:
        return False

    return True


def extract_quotable_lines(transcript: str) -> list[str]:
    """
    Sélectionne jusqu'à _MAX_QUOTES répliques distinctives du transcript,
    triées par longueur décroissante (plus une réplique est longue, plus
    elle est rare/unique sur le web, donc plus discriminante).
    """
    if not transcript or len(transcript.strip()) < 20:
        return []

    sentences = _split_sentences(transcript)
    quotable  = [s for s in sentences if _is_quotable(s)]
    quotable.sort(key=lambda s: len(s.split()), reverse=True)

    seen: set = set()
    result: list[str] = []
    for q in quotable:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            result.append(q)
        if len(result) >= _MAX_QUOTES:
            break

    return result


# ════════════════════════════════════════════════════════════════
# RECHERCHE WEB DE LA RÉPLIQUE EXACTE
# ════════════════════════════════════════════════════════════════

async def _search_quote_verbatim(quote: str) -> list[dict]:
    """
    Cherche la réplique exacte entre guillemets. Les sites qui indexent
    des répliques de films (bases de sous-titres, quotes IMDb, forums de
    fans) remontent naturellement dans les résultats DDG pour ce type
    de requête entre guillemets.
    """
    query = f'"{quote}" movie OR film OR series quote'
    results = await _ddg_search(query, max_results=6)
    if results:
        return results

    # Fallback sans contexte "movie/film" si la requête stricte échoue —
    # certaines répliques sont indexées sans ce mot-clé additionnel.
    query_loose = f'"{quote}"'
    return await _ddg_search(query_loose, max_results=6)


# ════════════════════════════════════════════════════════════════
# PIPELINE COMPLET : transcript → répliques → titres corroborés
# ════════════════════════════════════════════════════════════════

async def find_quote_corroboration(
    transcript: str,
    browser_lang: str = "fr",
    max_tmdb_candidates: int = 5,
) -> dict:
    """
    Point d'entrée principal. Ne lève jamais d'exception : en cas d'échec
    ou d'absence de réplique exploitable, retourne des listes vides.

    Retourne :
      {
        "candidates":     [...],  # candidats TMDB validés (format rerank())
        "quotes_used":    [...],  # répliques effectivement cherchées
        "matched_titles": [...],  # titres bruts extraits des snippets web
      }
    """
    empty = {"candidates": [], "quotes_used": [], "matched_titles": []}

    quotes = extract_quotable_lines(transcript)
    if not quotes:
        return empty

    print(f"💬 Répliques citables extraites: {quotes}", flush=True)

    all_web_results: list[dict] = []
    for i, quote in enumerate(quotes):
        results = await _search_quote_verbatim(quote)
        if results:
            print(f"  💬 Réplique '{quote[:50]}' → {len(results)} résultats web", flush=True)
            all_web_results.extend(results)
        if i < len(quotes) - 1:
            await asyncio.sleep(0.4)

    if not all_web_results:
        print("💬 Aucune réplique n'a donné de résultat web exploitable", flush=True)
        return {**empty, "quotes_used": quotes}

    # ── Extraction des titres depuis les snippets ──────────────────
    candidate_titles: list[str] = []
    seen_titles: set = set()
    for r in all_web_results:
        titles = _extract_titles_from_snippet(r.get("title", ""), r.get("snippet", ""))
        for t in titles:
            if t.lower() not in seen_titles:
                seen_titles.add(t.lower())
                candidate_titles.append(t)

    if not candidate_titles:
        print("💬 Réplique trouvée mais aucun titre extractible des snippets", flush=True)
        return {**empty, "quotes_used": quotes}

    print(f"💬 Titres extraits via réplique: {candidate_titles[:5]}", flush=True)

    # ── Validation TMDB de chaque titre candidat ────────────────────
    from data.tmdb import search_multi_lang

    tmdb_candidates: list[dict] = []
    seen_ids: set = set()
    for titre in candidate_titles[:6]:
        try:
            results = await search_multi_lang(titre, browser_lang=browser_lang)
            for item in results[:2]:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    item["_quote_match_origin"] = titre
                    tmdb_candidates.append(item)
        except Exception as e:
            print(f"⚠️ TMDB validation (quote) KO pour '{titre[:30]}': {e}", flush=True)
        if len(tmdb_candidates) >= max_tmdb_candidates:
            break

    print(
        f"✅ Quote corroboration → {len(tmdb_candidates)} candidats TMDB "
        f"(depuis {len(quotes)} répliques)",
        flush=True
    )

    return {
        "candidates":     tmdb_candidates[:max_tmdb_candidates],
        "quotes_used":    quotes,
        "matched_titles": candidate_titles[:6],
    }