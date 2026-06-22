"""
core/reranker.py — Sélection du meilleur candidat TMDB (cascade Gemini → Qwen → Groq).

Cascade :
  0. Gemini Flash    → reranking LLM, prioritaire
  1. Qwen (DashScope) → fallback si Gemini KO ou score < seuil
  2. Groq Llama       → fallback si Qwen KO ou score < seuil
  3. Comparaison des résultats LLM sous le seuil → on garde le meilleur
  4. Match direct     → correspondance titre (0 API), après échec de tous les LLM
  5. Heuristique popularité TMDB (0 API)
"""

import json
import os
import re
import httpx
from typing import Optional, List, Dict, Any

from core.prompts import RERANK_PROMPT

# ═══════════════════════════ CONFIGURATION ═══════════════════════════
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
GROQ_TEXT_URL   = "https://api.groq.com/openai/v1/chat/completions"
QWEN_TEXT_URL   = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
QWEN_TEXT_MODEL = "qwen-plus"
GROQ_CONFIDENCE_THRESHOLD = 40

# ═══════════════════════════ UTILITAIRES ═══════════════════════════

def _normalize(s: str) -> str:
    """Normalise une chaîne pour comparaison : minuscule, sans ponctuation, espaces unifiés."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _clean_json_fences(text: str) -> str:
    """Extrait le premier objet JSON trouvé, même entouré de markdown."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text.strip()

def _candidates_for_prompt(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Réduit les candidats aux champs utiles pour le LLM (économie de tokens)."""
    return [
        {
            "id":           c.get("id"),
            "title":        c.get("title") or c.get("name") or "",
            "release_date": (c.get("release_date") or c.get("first_air_date") or "")[:4],
            "overview":     (c.get("overview") or "")[:200],  # tronqué à 200 car.
            "vote_average": c.get("vote_average"),
            "media_type":   c.get("media_type", "movie"),
        }
        for c in candidates[:15]
    ]

def _parse_rerank_response(text: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse la réponse JSON d'un LLM et valide l'id candidat."""
    text = _clean_json_fences(text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f" Rerank JSON KO: {e} | raw={(text or 'N/A')[:120]}", flush=True)
        raise ValueError("Impossible de parser le JSON")

    candidate_ids = {c["id"] for c in candidates}
    result_id = result.get("id")

    # Fallback si l'id n'est pas dans la liste
    if not result_id or result_id not in candidate_ids:
        best = max(candidates, key=lambda c: c.get("popularity", 0), default=candidates[0])
        print(f" Rerank: id={result_id!r} invalide → fallback popularité ({best.get('title') or best.get('name')})", flush=True)
        return {
            "id": best["id"],
            "meilleur_titre": best.get("title") or best.get("name", "Inconnu"),
            "score": 30,
            "raison": "fallback_id_invalide",
            "media_type": best.get("media_type", "movie")
        }

    # Compléter les champs manquants
    if not result.get("meilleur_titre"):
        matched = next((c for c in candidates if c["id"] == result_id), {})
        result["meilleur_titre"] = matched.get("title") or matched.get("name") or "Inconnu"
    if "score" not in result or result["score"] is None:
        result["score"] = 50
    if not result.get("media_type"):
        matched = next((c for c in candidates if c["id"] == result_id), {})
        result["media_type"] = matched.get("media_type", "movie")

    return result

def _build_groq_messages(prompt: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Construit le contexte système pour forcer un JSON valide avec l'id candidat."""
    valid_ids = [str(c["id"]) for c in candidates[:15]]
    ids_str = ", ".join(valid_ids)
    return [
        {
            "role": "system",
            "content": (
                "Tu es un expert en cinéma et séries TV du monde entier. "
                "Réponds UNIQUEMENT en JSON minifié sur une seule ligne, sans markdown. "
                f"Tu DOIS choisir un id parmi cette liste exacte : [{ids_str}]. "
                "Ne retourne JAMAIS id=null ou un id absent de cette liste. "
                "Format EXACT attendu (une seule ligne) : "
                '{"id":123,"meilleur_titre":"Titre","score":75,"raison":"courte"}'
            ),
        },
        {"role": "user", "content": prompt},
    ]

def _best_by_popularity(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fallback ultime : sélection basée sur vote_average * vote_count."""
    def pop_score(c):
        va = c.get("vote_average") or 0
        vc = c.get("vote_count") or 0
        return va * vc

    best = max(candidates, key=pop_score, default=candidates[0])
    print(
        f" Rerank heuristique popularité → "
        f"{best.get('title') or best.get('name')} "
        f"(va={best.get('vote_average')}, vc={best.get('vote_count')})",
        flush=True
    )
    return {
        "id": best["id"],
        "meilleur_titre": best.get("title") or best.get("name", "Inconnu"),
        "score": 35,
        "raison": "fallback_popularite",
        "media_type": best.get("media_type", "movie")
    }

# ═══════════════════════════ NIVEAU 4 – MATCH DIRECT (utilisé seulement en fallback) ═══════════════
def _direct_match(extraction: dict, candidates: list) -> Optional[dict]:
    """
    Vérifie si un titre extrait correspond exactement à un titre candidat.
    Ajoute une vérification de cohérence description/synopsis pour éviter les faux positifs.
    Utilisé uniquement après échec de tous les LLM.
    """
    titres = [
        _normalize(str(t))
        for t in extraction.get("titres_possibles", [])
        if t and not str(t).startswith("?")
    ]
    if not titres:
        return None

    annee       = str(extraction.get("annee_estimee") or "")
    description = (extraction.get("description_courte") or "").lower()

    for c in candidates:
        c_title = _normalize(c.get("title") or c.get("name") or "")
        if c_title not in titres:
            continue

        c_year     = (c.get("release_date") or c.get("first_air_date") or "")[:4]
        c_overview = (c.get("overview") or "").lower()

        # Score de base
        score = 90 if (annee and annee == c_year) else 85

        # Vérification anti-faux-positif par les descriptions
        if description and c_overview:
            desc_keywords = [
                w for w in re.findall(r'\b\w{5,}\b', description)
                if w not in {
                    "femme", "homme", "enfant", "scène", "personnage",
                    "monde", "après", "avant", "contre", "depuis",
                }
            ]
            if desc_keywords:
                matches     = sum(1 for kw in desc_keywords if kw in c_overview)
                match_ratio = matches / len(desc_keywords)
                if match_ratio < 0.15 and len(desc_keywords) >= 3:
                    print(
                        f" Match direct '{c_title}' suspect "
                        f"(cohérence desc/synopsis={match_ratio:.0%}) "
                        f"→ score abaissé à 45",
                        flush=True
                    )
                    score = 45

        print(
            f" Rerank direct — {c.get('title') or c.get('name')} "
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

# ═══════════════════════════ FONCTIONS LLM ════════════════════════

async def _rerank_gemini(extraction: dict, candidates: list) -> Optional[dict]:
    """Niveau 0 – Gemini Flash (appel prioritaire)."""
    if not GEMINI_API_KEY:
        return None
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(
            _candidates_for_prompt(candidates), ensure_ascii=False
        ),
    )
    forced_prompt = (
        "INSTRUCTION ABSOLUE : réponds UNIQUEMENT avec un objet JSON minifié "
        "sur UNE SEULE LIGNE. AUCUN texte avant ou après. AUCUN markdown. "
        "Format exact : "
        '{"id":123,"meilleur_titre":"Titre","score":75,"raison":"courte"}\n\n'
        + prompt
    )
    text = None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "system_instruction": {
                        "parts": [{
                            "text": (
                                "Tu es un expert en cinéma et séries TV du monde entier. "
                                "Réponds UNIQUEMENT avec un objet JSON minifié sur une seule ligne. "
                                "AUCUN texte avant ou après le JSON. AUCUN markdown. "
                                "Format exact attendu : "
                                '{"id":123,"meilleur_titre":"Titre","score":75,"raison":"courte"}'
                            )
                        }]
                    },
                    "contents": [
                        {"role": "user", "parts": [{"text": forced_prompt}]}
                    ],
                    "generationConfig": {
                        "temperature":      0.0,
                        "maxOutputTokens":  150,
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
        print(f"✅ Rerank Gemini — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except json.JSONDecodeError as e:
        raw = text or "N/A"
        print(f"⚠️ Rerank Gemini JSON KO: {e} | raw={raw[:120]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Rerank Gemini KO: {str(e)[:120]}", flush=True)
        return None

async def _rerank_qwen(extraction: dict, candidates: list) -> Optional[dict]:
    """Niveau 1 – Qwen (DashScope), fallback après Gemini."""
    if not DASHSCOPE_API_KEY:
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
                QWEN_TEXT_URL,
                headers={
                    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": QWEN_TEXT_MODEL,
                    "messages": _build_groq_messages(prompt, candidates),
                    "temperature": 0.0,
                    "max_tokens": 150,
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code == 429:
                print("⚠️ Rerank Qwen: quota/rate limit", flush=True)
                return None
            resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_rerank_response(text, candidates)
        print(f"✅ Rerank Qwen — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Rerank Qwen JSON KO: {e} | raw={(text or 'N/A')[:120]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Rerank Qwen KO: {str(e)[:120]}", flush=True)
        return None

async def _rerank_groq(extraction: dict, candidates: list) -> Optional[dict]:
    """Niveau 2 – Groq Llama, dernier LLM de la cascade."""
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
                    "max_tokens":  150,
                },
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
            )
            resp.raise_for_status()
        text   = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_rerank_response(text, candidates)
        print(f"✅ Rerank Groq — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except json.JSONDecodeError as e:
        raw = text or "N/A"
        print(f"⚠️ Rerank Groq JSON KO: {e} | raw={raw[:120]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Rerank Groq KO: {str(e)[:120]}", flush=True)
        return None

# ═══════════════════════════ POINT D'ENTRÉE ═══════════════════════

async def rerank(extraction: dict, candidates: list) -> dict:
    """
    Choisit le meilleur candidat TMDB avec cascade Gemini → Qwen → Groq → match direct → popularité.
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

    # ── 0. Gemini Flash (prioritaire) ──
    gemini_result = await _rerank_gemini(extraction, candidates)
    if gemini_result and gemini_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return gemini_result
    if gemini_result:
        print(f"⚠️ Gemini score faible ({gemini_result['score']}) → tentative Qwen", flush=True)

    # ── 1. Qwen ──
    qwen_result = await _rerank_qwen(extraction, candidates)
    if qwen_result and qwen_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return qwen_result
    if qwen_result:
        print(f"⚠️ Qwen score faible ({qwen_result['score']}) → tentative Groq", flush=True)

    # ── 2. Groq ──
    groq_result = await _rerank_groq(extraction, candidates)
    if groq_result and groq_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return groq_result
    if groq_result:
        print(f"⚠️ Groq score faible ({groq_result['score']}) → aucun LLM n'a atteint le seuil", flush=True)

    # ── 3. Comparaison des LLM sous le seuil ──
    llm_results = [r for r in [gemini_result, qwen_result, groq_result] if r is not None]
    if llm_results:
        best_llm = max(llm_results, key=lambda r: r.get("score", 0))
        print(
            f"⚠️ Aucun LLM n'a atteint le seuil → meilleur score retenu : "
            f"{best_llm['meilleur_titre']} ({best_llm['score']})",
            flush=True
        )
        return best_llm

    # ── 4. Match direct (fallback après échec complet des LLM) ──
    direct_result = _direct_match(extraction, candidates)
    if direct_result:
        print(
            f"⚠️ LLM tous KO → utilisation match direct "
            f"({direct_result['meilleur_titre']}, score={direct_result['score']})",
            flush=True
        )
        return direct_result

    # ── 5. Heuristique popularité ──
    return _best_by_popularity(candidates)