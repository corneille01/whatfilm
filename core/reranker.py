"""
core/reranker.py — Sélection du meilleur candidat TMDB.

Cascade anti-coût :
  1. Score direct    → titre extrait == candidat (0 API)
  2. Groq Llama      → reranking LLM texte, gratuit
  3. Gemini Flash    → fallback si Groq KO ou score < 40
  4. Heuristique     → popularité TMDB (0 API)

Fixes v4 :
  - Gemini appelé si score Groq < 40 (Groq peu fiable sur les séries TV)
  - _candidates_for_prompt : passe les 15 premiers au lieu de 10
  - _best_by_popularity : suppression de la pénalité TV (biais injustifié)
  - logs : affiche le score Groq avant de décider si fallback Gemini
"""

import json
import os
import re
import httpx

from core.prompts import RERANK_PROMPT

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
GROQ_TEXT_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

# Seuil en dessous duquel on considère que Groq est peu sûr → fallback Gemini
GROQ_CONFIDENCE_THRESHOLD = 40


# ════════════════════════════════════════════════════════════════
# NIVEAU 0 — Match direct titre (0 API)
# ════════════════════════════════════════════════════════════════

def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _direct_match(extraction: dict, candidates: list) -> dict | None:
    titres = [
        _normalize(str(t))
        for t in extraction.get("titres_possibles", [])
        if t and not str(t).startswith("?")
    ]
    annee = str(extraction.get("annee_estimee") or "")

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
                "media_type":     c.get("media_type", "movie"),
            }
    return None


# ════════════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════════════

def _clean_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text.strip()


def _candidates_for_prompt(candidates: list) -> list:
    """
    Prépare les candidats pour le prompt LLM.
    On passe les 15 premiers (au lieu de 10) pour donner plus de contexte,
    notamment quand les séries TV sont en fin de liste.
    """
    return [
        {
            "id":           c.get("id"),
            "title":        c.get("title") or c.get("name") or "",
            "release_date": (c.get("release_date") or c.get("first_air_date") or "")[:4],
            "overview":     (c.get("overview") or "")[:200],
            "vote_average": c.get("vote_average"),
            "media_type":   c.get("media_type", "movie"),
        }
        for c in candidates[:15]
    ]


def _parse_rerank_response(text: str, candidates: list) -> dict:
    """
    Parse la réponse LLM et retourne un dict valide.

    - score=0 accepté (= incertitude, pas erreur)
    - id=None ou id absent des candidats → fallback sur le candidat
      le plus populaire, score plafonné à 30
    """
    text   = _clean_json_fences(text)
    result = json.loads(text)

    if not isinstance(result, dict):
        raise ValueError(f"Réponse non-dict : {type(result)}")

    candidate_ids = {c["id"] for c in candidates}

    result_id = result.get("id")
    if not result_id or result_id not in candidate_ids:
        best = max(candidates, key=lambda c: c.get("popularity", 0), default=None)
        if not best:
            raise ValueError("id invalide et aucun candidat disponible")
        print(
            f"⚠️ Rerank: id={result_id!r} invalide → fallback popularité "
            f"({best.get('title') or best.get('name')})",
            flush=True
        )
        result["id"]             = best["id"]
        result["meilleur_titre"] = best.get("title") or best.get("name") or "Inconnu"
        result["media_type"]     = best.get("media_type", "movie")
        result["score"]          = min(result.get("score") or 30, 30)
        result["raison"]         = (result.get("raison") or "") + " [id fallback popularité]"
        return result

    if not result.get("meilleur_titre"):
        matched = next((c for c in candidates if c.get("id") == result_id), None)
        result["meilleur_titre"] = (
            (matched.get("title") or matched.get("name") or "Inconnu")
            if matched else "Inconnu"
        )

    if not result.get("media_type"):
        matched = next((c for c in candidates if c.get("id") == result_id), None)
        if matched:
            result["media_type"] = matched.get("media_type", "movie")

    if "score" not in result or result["score"] is None:
        result["score"] = 50

    return result


def _build_groq_messages(prompt: str, candidates: list) -> list:
    valid_ids = [str(c["id"]) for c in candidates[:15]]
    ids_str   = ", ".join(valid_ids)

    return [
        {
            "role": "system",
            "content": (
                "Tu es un expert en cinéma et séries TV du monde entier. "
                "Réponds UNIQUEMENT en JSON valide, sans markdown ni explication. "
                f"Tu DOIS choisir un id parmi cette liste exacte : [{ids_str}]. "
                "Ne retourne JAMAIS id=null ou un id absent de cette liste. "
                "Si tu n'es pas sûr, choisis l'id le plus probable et mets "
                "score entre 20 et 49. "
                "Ne mets score=0 que si vraiment aucun candidat ne correspond, "
                "mais tu dois quand même choisir un id valide de la liste."
            ),
        },
        {"role": "user", "content": prompt},
    ]


def _best_by_popularity(candidates: list) -> dict:
    """
    Heuristique finale : trier par vote_count × vote_average.
    Pas de pénalité TV — une série populaire vaut autant qu'un film populaire.
    """
    def pop_score(c):
        va = c.get("vote_average") or 0
        vc = c.get("vote_count")   or 0
        return va * vc

    best = max(candidates, key=pop_score)
    print(
        f"⚠️ Rerank heuristique popularité → "
        f"{best.get('title') or best.get('name')} "
        f"(va={best.get('vote_average')}, vc={best.get('vote_count')})",
        flush=True
    )
    return {
        "id":             best.get("id"),
        "meilleur_titre": best.get("title") or best.get("name") or "Inconnu",
        "score":          35,
        "raison":         "fallback popularité",
        "media_type":     best.get("media_type", "movie"),
    }


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Groq Llama texte
# ════════════════════════════════════════════════════════════════

async def _rerank_groq(extraction: dict, candidates: list) -> dict | None:
    if not GROQ_API_KEY:
        return None

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(
            _candidates_for_prompt(candidates), ensure_ascii=False
        ),
    )

    text = None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                GROQ_TEXT_URL,
                json={
                    "model":       GROQ_TEXT_MODEL,
                    "messages":    _build_groq_messages(prompt, candidates),
                    "temperature": 0.0,
                    "max_tokens":  512,
                },
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
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

    except json.JSONDecodeError as e:
        raw = text or "N/A"
        print(f"⚠️ Rerank Groq JSON KO: {e} | raw={raw[:120]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Rerank Groq KO: {str(e)[:120]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# NIVEAU 2 — Gemini Flash (fallback si Groq KO ou score < seuil)
# ════════════════════════════════════════════════════════════════

async def _rerank_gemini(extraction: dict, candidates: list) -> dict | None:
    if not GEMINI_API_KEY:
        return None

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(
            _candidates_for_prompt(candidates), ensure_ascii=False
        ),
    )

    text = None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [
                        {"role": "user", "parts": [{"text": prompt}]}
                    ],
                    "generationConfig": {
                        "temperature":      0.0,
                        "maxOutputTokens":  512,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()

        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts",    [{}])[0]
            .get("text", "")
        ).strip()

        if not text:
            print("⚠️ Rerank Gemini réponse vide", flush=True)
            return None

        result = _parse_rerank_response(text, candidates)
        print(
            f"✅ Rerank Gemini — {result['meilleur_titre']} "
            f"(score={result['score']})",
            flush=True
        )
        return result

    except json.JSONDecodeError as e:
        raw = text or "N/A"
        print(f"⚠️ Rerank Gemini JSON KO: {e} | raw={raw[:120]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Rerank Gemini KO: {str(e)[:120]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════

async def rerank(extraction: dict, candidates: list) -> dict:
    """
    Retourne toujours un dict valide : {id, meilleur_titre, score, media_type, raison?}

    Cascade :
      0. Match direct titre (0 API)
      1. Groq Llama
         → si score >= GROQ_CONFIDENCE_THRESHOLD : retourne le résultat
         → si score < seuil : tente Gemini pour confirmation
      2. Gemini Flash (fallback Groq KO ou score bas)
         → si Gemini score > Groq score : retourne Gemini
         → sinon : retourne Groq quand même (mieux que rien)
      3. Heuristique popularité (0 API)
    """
    if not candidates:
        return {"meilleur_titre": "Inconnu", "id": None, "score": 0, "media_type": "movie"}

    if len(candidates) == 1:
        c = candidates[0]
        return {
            "id":             c.get("id"),
            "meilleur_titre": c.get("title") or c.get("name") or "Inconnu",
            "score":          55,
            "raison":         "candidat unique",
            "media_type":     c.get("media_type", "movie"),
        }

    # ── 0. Correspondance directe (0 API) ────────────────────────
    result = _direct_match(extraction, candidates)
    if result:
        return result

    # ── 1. Groq Llama ─────────────────────────────────────────────
    groq_result = await _rerank_groq(extraction, candidates)

    if groq_result and groq_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        # Groq confiant → pas besoin de Gemini
        return groq_result

    if groq_result:
        print(
            f"⚠️ Groq score faible ({groq_result['score']} < {GROQ_CONFIDENCE_THRESHOLD}) "
            f"→ tentative Gemini pour confirmation",
            flush=True
        )

    # ── 2. Gemini Flash ───────────────────────────────────────────
    gemini_result = await _rerank_gemini(extraction, candidates)

    if gemini_result and groq_result:
        # Les deux ont répondu : prendre le meilleur score
        if gemini_result.get("score", 0) >= groq_result.get("score", 0):
            print(
                f"✅ Gemini retenu sur Groq "
                f"({gemini_result['score']} >= {groq_result['score']})",
                flush=True
            )
            return gemini_result
        else:
            print(
                f"✅ Groq retenu sur Gemini "
                f"({groq_result['score']} > {gemini_result['score']})",
                flush=True
            )
            return groq_result

    if gemini_result:
        return gemini_result

    if groq_result:
        # Groq seul, score bas mais mieux que heuristique
        return groq_result

    # ── 3. Heuristique popularité (0 API) ─────────────────────────
    return _best_by_popularity(candidates)