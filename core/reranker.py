"""
core/reranker.py — Sélection du meilleur candidat TMDB.

Cascade anti-coût :
  1. Score direct    → si un candidat matche exactement un titre extrait (0 API)
  2. Groq Llama      → reranking LLM texte, gratuit
  3. Gemini Flash    → fallback si Groq KO
  4. Heuristique     → premier candidat, score 35 (0 API)
"""

import json
import os
import re
import httpx
import traceback

from core.prompts import RERANK_PROMPT

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
GROQ_TEXT_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"


# ════════════════════════════════════════════════════════════════
# NIVEAU 0 — Score direct par correspondance de titre (0 API)
# ════════════════════════════════════════════════════════════════
def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _direct_match(extraction: dict, candidates: list) -> dict | None:
    titres = [_normalize(str(t)) for t in extraction.get("titres_possibles", []) if t]
    annee  = str(extraction.get("annee_estimee") or "")

    for c in candidates:
        c_title = _normalize(c.get("title") or c.get("name") or "")
        if not c_title:
            continue
        if c_title in titres:
            c_year = (c.get("release_date") or c.get("first_air_date") or "")[:4]
            score  = 90 if (annee and annee == c_year) else 85
            print(
                f"✅ Rerank direct — {c.get('title') or c.get('name')} "
                f"(score={score})",
                flush=True
            )
            return {
                "id":             c["id"],
                "meilleur_titre": c.get("title") or c.get("name") or "Inconnu",
                "score":          score,
                "raison":         "correspondance directe titre",
            }
    return None


# ════════════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════════════
def _clean_json_fences(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                json.loads(part)
                return part
            except Exception:
                continue
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text


def _parse_rerank_response(text: str, candidates: list) -> dict:
    text   = _clean_json_fences(text)
    result = json.loads(text)

    if not isinstance(result, dict):
        raise ValueError(f"Réponse non-dict : {type(result)}")
    if not result.get("id"):
        raise ValueError(f"id manquant : {result}")

    if not result.get("meilleur_titre"):
        matched = next((c for c in candidates if c.get("id") == result.get("id")), None)
        result["meilleur_titre"] = (
            (matched.get("title") or matched.get("name") or "Inconnu")
            if matched else "Inconnu"
        )
    if "score" not in result:
        result["score"] = 20

    return result


def _candidates_for_prompt(candidates: list) -> list:
    return [
        {
            "id":           c.get("id"),
            "title":        c.get("title") or c.get("name") or "",
            "release_date": (c.get("release_date") or c.get("first_air_date") or "")[:4],
            "overview":     (c.get("overview") or "")[:200],
            "vote_average": c.get("vote_average"),
            "media_type":   c.get("media_type", "movie"),
        }
        for c in candidates[:10]
    ]


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Groq Llama texte
# ════════════════════════════════════════════════════════════════
async def _rerank_groq(extraction: dict, candidates: list) -> dict | None:
    if not GROQ_API_KEY:
        return None

    # On filtre l'extraction pour ne garder que les champs utiles au rerank
    extraction_for_prompt = {
        "titres_possibles":  extraction.get("titres_possibles", []),
        "acteurs":           extraction.get("acteurs", []),
        "personnages":       extraction.get("personnages", []),
        "objets_importants": extraction.get("objets_importants", []),
        "indices_visuels":   extraction.get("indices_visuels", []),
        "description_courte": extraction.get("description_courte", ""),
        "genre_apparent":    extraction.get("genre_apparent", ""),
        "annee_estimee":     extraction.get("annee_estimee"),
        "langue_originale":  extraction.get("langue_originale", ""),
    }

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction_for_prompt, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
    )

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                GROQ_TEXT_URL,
                json={
                    "model": GROQ_TEXT_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Tu es un expert en cinéma et séries TV du monde entier. "
                                "Réponds UNIQUEMENT en JSON valide sur une seule ligne, sans markdown."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens":  256,
                },
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json"
                }
            )
            resp.raise_for_status()

        text   = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_rerank_response(text, candidates)
        print(
            f"✅ Rerank Groq — {result['meilleur_titre']} "
            f"(score={result['score']})",
            flush=True
        )
        return result

    except Exception as e:
        print(f"⚠️ Rerank Groq KO: {str(e)[:120]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# NIVEAU 2 — Gemini Flash (fallback si Groq KO)
# ════════════════════════════════════════════════════════════════
async def _rerank_gemini(extraction: dict, candidates: list) -> dict | None:
    if not GEMINI_API_KEY:
        return None

    extraction_for_prompt = {
        "titres_possibles":  extraction.get("titres_possibles", []),
        "acteurs":           extraction.get("acteurs", []),
        "personnages":       extraction.get("personnages", []),
        "objets_importants": extraction.get("objets_importants", []),
        "indices_visuels":   extraction.get("indices_visuels", []),
        "description_courte": extraction.get("description_courte", ""),
        "genre_apparent":    extraction.get("genre_apparent", ""),
        "annee_estimee":     extraction.get("annee_estimee"),
        "langue_originale":  extraction.get("langue_originale", ""),
    }

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction_for_prompt, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
    )

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature":      0.0,
                        "maxOutputTokens":  256,
                        "responseMimeType": "application/json",
                    }
                }
            )
            resp.raise_for_status()

        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()

        result = _parse_rerank_response(text, candidates)
        print(
            f"✅ Rerank Gemini — {result['meilleur_titre']} "
            f"(score={result['score']})",
            flush=True
        )
        return result

    except Exception as e:
        print(f"⚠️ Rerank Gemini KO: {str(e)[:120]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
async def rerank(extraction: dict, candidates: list) -> dict:
    if not candidates:
        return {"meilleur_titre": "Inconnu", "id": None, "score": 0}

    # Cas trivial : un seul candidat
    if len(candidates) == 1:
        c = candidates[0]
        return {
            "id":             c.get("id"),
            "meilleur_titre": c.get("title") or c.get("name") or "Inconnu",
            "score":          55,
            "raison":         "candidat unique",
        }

    # ── 0. Correspondance directe (0 API) ────────────────────────
    result = _direct_match(extraction, candidates)
    if result:
        return result

    # ── 1. Groq Llama ─────────────────────────────────────────────
    result = await _rerank_groq(extraction, candidates)
    if result:
        return result

    # ── 2. Gemini Flash ───────────────────────────────────────────
    result = await _rerank_gemini(extraction, candidates)
    if result:
        return result

    # ── 3. Heuristique : premier candidat (0 API) ─────────────────
    best = candidates[0]
    print(
        f"⚠️ Rerank fallback heuristique → "
        f"{best.get('title') or best.get('name')}",
        flush=True
    )
    return {
        "id":             best.get("id"),
        "meilleur_titre": best.get("title") or best.get("name") or "Inconnu",
        "score":          35,
        "raison":         "fallback heuristique",
    }