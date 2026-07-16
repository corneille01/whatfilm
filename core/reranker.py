"""
core/reranker.py — Sélection du meilleur candidat TMDB (cascade Gemini → Qwen → Groq).

Cascade :
  0. Gemini Flash    → reranking LLM, prioritaire (désactivable via GEMINI_RERANK_DISABLED)
  1. Qwen (DashScope) → fallback si Gemini KO ou score < seuil
  2. Groq Llama       → fallback si Qwen KO ou score < seuil
  3. Comparaison des résultats LLM sous le seuil → on garde le meilleur
  4. Match direct     → correspondance titre (0 API), après échec de tous les LLM
  5. Heuristique popularité TMDB (0 API)

Cas "candidat unique" (v2) :
  Un seul candidat ne signifie pas un bon candidat. Si la cascade de recherche
  n'a remonté qu'un seul résultat via une requête peu fiable (mot générique,
  reste de transcript mal traduit, etc.), on vérifie une corroboration minimale
  (titre extrait par Gemini qui matche, ou acteur connu) avant d'accorder un
  score de confiance. Sans corroboration → score abaissé sous le seuil LLM,
  pour éviter de mettre en cache un faux positif avec une confiance artificielle.

Parsing JSON tolérant (v3) :
  Gemini (et parfois Qwen/Groq) ignore occasionnellement l'instruction de
  réponse JSON stricte et préfixe sa réponse d'un préambule en langage naturel
  ("Here is the JSON response:", "He..." tronqué par maxOutputTokens trop
  serré, etc.). _clean_json_fences cherche maintenant la première accolade
  ouvrante ET la dernière fermante n'importe où dans le texte plutôt que de
  supposer un format propre, et maxOutputTokens a été augmenté pour laisser
  de la marge à un préambule that le modèle ajouterait malgré l'instruction.
"""

import json
import os
import re
import httpx
from typing import Optional, List, Dict, Any
import asyncio
import random

from core.prompts import RERANK_PROMPT

# ═══════════════════════════ CONFIGURATION ═══════════════════════════
GEMINI_RERANK_DISABLED = os.environ.get("GEMINI_RERANK_DISABLED", "false").lower() == "true"
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

OPENROUTER_RERANK_ENABLED = (
    os.environ.get("OPENROUTER_RERANK_ENABLED", "true").lower() == "true"
)

OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
).rstrip("/")

OPENROUTER_RERANK_MODEL = os.environ.get(
    "OPENROUTER_RERANK_MODEL",
    "qwen/qwen3-next-80b-a3b-instruct:free",
)

OPENROUTER_SITE_URL = os.environ.get(
    "OPENROUTER_SITE_URL",
    "https://pelify.app",
)

OPENROUTER_APP_NAME = os.environ.get(
    "OPENROUTER_APP_NAME",
    "Pelify",
)

OPENROUTER_RERANK_MAX_TOKENS = int(
    os.environ.get("OPENROUTER_RERANK_MAX_TOKENS", "220")
)

GEMINI_URL    = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GROQ_TEXT_URL = "https://api.groq.com/openai/v1/chat/completions"
QWEN_TEXT_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"

GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
QWEN_TEXT_MODEL = "qwen-plus"
GROQ_CONFIDENCE_THRESHOLD = 40

# Score plancher pour un candidat unique sans aucune corroboration
# (titre/acteur extrait par Gemini qui ne matche pas le candidat trouvé)
UNCORROBORATED_SINGLE_CANDIDATE_SCORE = 25

# maxOutputTokens pour les appels de rerank. Augmenté de 100 → 200 :
# un préambule du type "Here is the JSON response: " ajouté malgré
# l'instruction stricte peut consommer 15-20 tokens, ce qui, combiné
# à un budget de 100 tokens, peut tronquer le JSON avant la fermeture
# de l'accolade et le rendre invalide même avec un parsing tolérant.
RERANK_MAX_OUTPUT_TOKENS = 200

# ═══════════════════════════ UTILITAIRES ═══════════════════════════

GEMINI_RERANK_MAX_RETRIES = 3
GEMINI_RERANK_BASE_DELAY  = 1.0


async def _post_with_retry_429(client: httpx.AsyncClient, url: str, **kwargs):
    last_exc = None
    for attempt in range(GEMINI_RERANK_MAX_RETRIES):
        try:
            resp = await client.post(url, **kwargs)
            if resp.status_code == 429 and attempt < GEMINI_RERANK_MAX_RETRIES - 1:
                delay = GEMINI_RERANK_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                print(f"⏳ Rerank 429, retry {attempt + 1}/{GEMINI_RERANK_MAX_RETRIES} dans {delay:.1f}s...", flush=True)
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < GEMINI_RERANK_MAX_RETRIES - 1:
                delay = GEMINI_RERANK_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                last_exc = e
                continue
            raise
    raise last_exc

def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _clean_json_fences(text: str) -> str:
    """
    Extrait un objet JSON d'une réponse LLM potentiellement "sale" :
      - bloc markdown ```json ... ```
      - préambule en langage naturel avant le JSON ("Here is the JSON: {...}")
      - texte après le JSON
    Cherche la première '{' et la dernière '}' dans tout le texte plutôt que
    de supposer un format propre dès le premier caractère.
    """
    text = text.strip()

    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            start = part.find("{")
            end   = part.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = part[start:end + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    continue

    # Pas de bloc markdown (ou aucun bloc valide trouvé) : on cherche
    # la première accolade ouvrante et la dernière fermante dans le
    # texte brut entier, peu importe ce qui les précède ou les suit.
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


def _try_extract_id_score_regex(text: str) -> Optional[Dict[str, Any]]:
    """
    Dernier recours si le JSON est tronqué/invalide même après nettoyage
    (ex: maxOutputTokens a coupé la réponse avant la fermeture de l'accolade).
    Extrait "id" et "score" directement par regex depuis le texte brut.
    Retourne None si même ce filet de sécurité ne trouve rien d'exploitable.
    """
    result: Dict[str, Any] = {}

    m_id = re.search(r'"id"\s*:\s*(\d+)', text)
    if m_id:
        result["id"] = int(m_id.group(1))

    m_score = re.search(r'"score"\s*:\s*(\d+)', text)
    if m_score:
        result["score"] = int(m_score.group(1))

    m_titre = re.search(r'"meilleur_titre"\s*:\s*"([^"]*)"', text)
    if m_titre:
        result["meilleur_titre"] = m_titre.group(1)

    if "id" not in result:
        return None

    return result

def _candidates_for_prompt(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _TIER_LABELS = {
        1: "titre_certain", 2: "acteur_connu", 3: "personnage",
        4: "indices_visuels_combines", 5: "mots_cles_description",
        6: "titre_incertain_vague", 7: "type_media", 8: "indice_seul",
    }
    return [
        {
            "id":           c.get("id"),
            "title":        c.get("title") or c.get("name") or "",
            "release_date": (c.get("release_date") or c.get("first_air_date") or "")[:4],
            "overview":     (c.get("overview") or "")[:200],
            "vote_average": c.get("vote_average"),
            "media_type":   c.get("media_type", "movie"),
            "match_origin": _TIER_LABELS.get(c.get("_match_tier"), "inconnu"),
        }
        for c in candidates[:15]
    ]
def _parse_rerank_response(text: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    cleaned = _clean_json_fences(text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Filet de sécurité : extraction regex avant d'abandonner complètement.
        # Utile quand maxOutputTokens tronque le JSON après "id" et "score"
        # mais avant la fermeture de l'accolade.
        fallback = _try_extract_id_score_regex(text)
        if fallback is not None:
            print(
                f"⚠️ Rerank JSON invalide mais extraction regex réussie: {fallback}",
                flush=True,
            )
            result = fallback
        else:
            print(f"⚠️ Rerank JSON KO: {e} | raw={(text or 'N/A')[:120]}", flush=True)
            raise ValueError("Impossible de parser le JSON")

    candidate_ids = {c["id"] for c in candidates}
    result_id     = result.get("id")

    if not result_id or result_id not in candidate_ids:
        best = max(candidates, key=lambda c: c.get("popularity", 0), default=candidates[0])
        print(f"⚠️ Rerank: id={result_id!r} invalide → fallback popularité ({best.get('title') or best.get('name')})", flush=True)
        return {
            "id":             best["id"],
            "meilleur_titre": best.get("title") or best.get("name", "Inconnu"),
            "score":          30,
            "raison":         "fallback_id_invalide",
            "media_type":     best.get("media_type", "movie"),
        }

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
    valid_ids = [str(c["id"]) for c in candidates[:15]]
    ids_str   = ", ".join(valid_ids)
    return [
        {
            "role": "system",
            "content": (
                "Tu es un expert en cinéma et séries TV du monde entier. "
                "Réponds UNIQUEMENT en JSON minifié sur une seule ligne, sans markdown. "
                f"Tu DOIS choisir un id parmi cette liste exacte : [{ids_str}]. "
                "Ne retourne JAMAIS id=null ou un id absent de cette liste. "
                'Format EXACT (une seule ligne, raison max 15 mots) : '
                '{"id":123,"meilleur_titre":"Titre","score":75,"raison":"bref"}'
            ),
        },
        {"role": "user", "content": prompt},
    ]

def _best_by_popularity(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Dernier recours absolu : aucun LLM n'a atteint le seuil, aucun match
    direct. On ne "devine" plus un titre populaire avec un score qui
    ressemble à un vrai résultat — le score est volontairement très bas
    (18, loin sous tout seuil de rejet) pour ne JAMAIS pouvoir être
    confondu avec une identification réelle. Le nom de la source
    ("popularity_guess" et non "cascade") permet aussi à confidence.py
    de la traiter différemment d'un vrai signal cascade.
    """
    def pop_score(c):
        return (c.get("vote_average") or 0) * (c.get("vote_count") or 0)
    best = max(candidates, key=pop_score, default=candidates[0])
    print(f"⚠️ Rerank heuristique popularité (devinette, PAS une identification) → {best.get('title') or best.get('name')}", flush=True)
    return {
        "id":             best["id"],
        "meilleur_titre": best.get("title") or best.get("name", "Inconnu"),
        "score":          18,
        "raison":         "fallback_popularite_devinette",
        "media_type":     best.get("media_type", "movie"),
        "is_guess":       True,
    }

# ═══════════════════════════ CORROBORATION CANDIDAT UNIQUE ═══════════════════

def _has_corroboration(extraction: dict, candidate: Dict[str, Any]) -> bool:
    """
    Vérifie si un candidat unique est corroboré par l'extraction Gemini :
      - un titre certain (sans '?') de l'extraction matche le titre du candidat
      - OU un acteur extrait avec confiance correspond (signal indirect, on ne
        vérifie pas le cast ici pour rester sans appel API supplémentaire —
        la présence d'acteurs fiables suffit à indiquer une extraction réussie,
        contrairement à un mot générique seul comme 'Prenons')

    Objectif : distinguer un vrai titre extrait par Gemini (signal fort) d'un
    reste de transcript/mot isolé qui a eu la chance de matcher un titre TMDB
    existant.
    """
    candidate_title = _normalize(candidate.get("title") or candidate.get("name") or "")
    if not candidate_title:
        return False

    titres_certains = [
        _normalize(str(t))
        for t in extraction.get("titres_possibles", [])
        if t and not str(t).startswith("?")
    ]
    if candidate_title in titres_certains:
        return True

    # Titre incertain mais précis (ex: "?Love, Death & Robots") qui matche quand même
    titres_incertains = [
        _normalize(str(t)[1:])
        for t in extraction.get("titres_possibles", [])
        if str(t).startswith("?") and len(str(t)) > 3
    ]
    if candidate_title in titres_incertains:
        return True

    # Acteurs avec certitude très élevée (≥90, cohérent avec le prompt d'extraction)
    acteurs    = extraction.get("acteurs", []) or []
    certitudes = extraction.get("acteurs_certitude", []) or []
    if acteurs and any(
        (c if isinstance(c, (int, float)) else 0) >= 90 for c in certitudes
    ):
        return True

    return False


def _single_candidate_result(extraction: dict, candidate: Dict[str, Any]) -> Dict[str, Any]:
    corroborated = _has_corroboration(extraction, candidate)
    score = 55 if corroborated else UNCORROBORATED_SINGLE_CANDIDATE_SCORE
    raison = "candidat unique corroboré" if corroborated else "candidat unique non corroboré"

    if not corroborated:
        print(
            f"⚠️ Candidat unique SANS corroboration — "
            f"{candidate.get('title') or candidate.get('name')} "
            f"(score abaissé à {score})",
            flush=True,
        )

    return {
        "id":             candidate.get("id"),
        "meilleur_titre": candidate.get("title") or candidate.get("name") or "Inconnu",
        "score":          score,
        "raison":         raison,
        "media_type":     candidate.get("media_type", "movie"),
    }

# ═══════════════════════════ MATCH DIRECT ═══════════════════════════

def _direct_match(extraction: dict, candidates: list) -> Optional[dict]:
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
        score      = 90 if (annee and annee == c_year) else 85

        if description and c_overview:
            desc_keywords = [
                w for w in re.findall(r'\b\w{5,}\b', description)
                if w not in {"femme", "homme", "enfant", "scène", "personnage",
                             "monde", "après", "avant", "contre", "depuis"}
            ]
            if desc_keywords:
                matches     = sum(1 for kw in desc_keywords if kw in c_overview)
                match_ratio = matches / len(desc_keywords)
                if match_ratio < 0.15 and len(desc_keywords) >= 3:
                    print(f"⚠️ Match direct '{c_title}' suspect (cohérence={match_ratio:.0%}) → score 45", flush=True)
                    score = 45

        print(f"⚠️ Rerank direct — {c.get('title') or c.get('name')} (score={score})", flush=True)
        return {
            "id":             c["id"],
            "meilleur_titre": c.get("title") or c.get("name") or "Inconnu",
            "score":          score,
            "raison":         "correspondance directe titre",
            "media_type":     c.get("media_type", "movie"),
        }
    return None

# ═══════════════════════════ FONCTIONS LLM ════════════════════════
async def _rerank_openrouter(extraction: dict, candidates: list) -> Optional[dict]:
    """
    Rerank via OpenRouter, placé en première tentative.
    Si OpenRouter échoue, rate-limit, ou retourne un JSON invalide,
    la cascade continue vers Gemini/Qwen/Groq.
    """
    if not OPENROUTER_RERANK_ENABLED:
        return None

    if not OPENROUTER_API_KEY:
        return None

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
    )

    forced_prompt = (
        "INSTRUCTION ABSOLUE : réponds UNIQUEMENT avec un objet JSON minifié "
        "sur UNE SEULE LIGNE. AUCUN texte avant ou après. AUCUN markdown. "
        "La raison doit faire moins de 15 mots. "
        'Format exact : {"id":123,"meilleur_titre":"Titre","score":75,"raison":"bref"}\n\n'
        + prompt
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
        "X-OpenRouter-Title": OPENROUTER_APP_NAME,
    }

    payload = {
    "model": OPENROUTER_RERANK_MODEL,
    "messages": [
        {
            "role": "system",
            "content": (
                "Tu es un moteur de reranking cinéma. "
                "Tu dois choisir uniquement parmi les candidats fournis. "
                "Réponds uniquement en JSON valide. "
                "Aucun raisonnement, aucun markdown, aucun texte hors JSON."
            ),
        },
        {
            "role": "user",
            "content": forced_prompt,
        },
    ],
    "temperature": 0.0,
    "max_tokens": OPENROUTER_RERANK_MAX_TOKENS,

    # IMPORTANT : empêche les réponses du type
    # "The user wants me to..."
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "pelify_rerank",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": ["integer", "null"]
                    },
                    "meilleur_titre": {
                        "type": "string"
                    },
                    "score": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100
                    },
                    "raison": {
                        "type": "string"
                    }
                },
                "required": ["id", "meilleur_titre", "score", "raison"],
                "additionalProperties": False
            }
        }
    },

    # Optionnel mais utile avec certains modèles OpenRouter
    "plugins": [
        {
            "id": "response-healing"
        }
    ],
}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )

        if resp.status_code == 429:
            print("⚠️ Rerank OpenRouter: rate-limit/quota → Gemini", flush=True)
            return None

        if resp.status_code >= 400:
            print(
                f"⚠️ Rerank OpenRouter HTTP {resp.status_code}: {resp.text[:180]}",
                flush=True,
            )
            return None

        raw = resp.json()
        content = (
            raw.get("choices", [{}])[0]
               .get("message", {})
               .get("content", "")
        )

        if isinstance(content, list):
            text = "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ).strip()
        else:
            text = str(content or "").strip()

        if not text:
            print("⚠️ Rerank OpenRouter réponse vide", flush=True)
            return None

        result = _parse_rerank_response(text, candidates)
        print(
            f"✅ Rerank OpenRouter — {result['meilleur_titre']} "
            f"(score={result['score']})",
            flush=True,
        )
        return result

    except Exception as e:
        print(f"⚠️ Rerank OpenRouter KO: {str(e)[:120]}", flush=True)
        return None
    
async def _rerank_gemini(extraction: dict, candidates: list) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
    )
    forced_prompt = (
        "INSTRUCTION ABSOLUE : réponds UNIQUEMENT avec un objet JSON minifié "
        "sur UNE SEULE LIGNE. AUCUN texte avant ou après. AUCUN markdown. "
        "La raison doit faire moins de 15 mots. "
        'Format exact : {"id":123,"meilleur_titre":"Titre","score":75,"raison":"bref"}\n\n'
        + prompt
    )
    text = None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await _post_with_retry_429(client, f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "system_instruction": {
                        "parts": [{"text": (
                            "Tu es un expert en cinéma et séries TV du monde entier. "
                            "Réponds UNIQUEMENT avec un objet JSON minifié sur une seule ligne. "
                            "AUCUN texte avant ou après. AUCUN markdown. "
                            'Format : {"id":123,"meilleur_titre":"Titre","score":75,"raison":"bref"}'
                        )}]
                    },
                    "contents": [{"role": "user", "parts": [{"text": forced_prompt}]}],
                    "generationConfig": {
                        "temperature":      0.0,
                        "maxOutputTokens":  RERANK_MAX_OUTPUT_TOKENS,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()
        if not text:
            print("⚠️ Rerank Gemini réponse vide", flush=True)
            return None
        result = _parse_rerank_response(text, candidates)
        print(f"✅ Rerank Gemini — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except Exception as e:
        print(f"⚠️ Rerank Gemini KO: {str(e)[:120]}", flush=True)
        return None

async def _rerank_qwen(extraction: dict, candidates: list) -> Optional[dict]:
    if not DASHSCOPE_API_KEY:
        return None
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
    )
    text = None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                QWEN_TEXT_URL,
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model":           QWEN_TEXT_MODEL,
                    "messages":        _build_groq_messages(prompt, candidates),
                    "temperature":     0.0,
                    "max_tokens":      RERANK_MAX_OUTPUT_TOKENS,
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code == 429:
                print("⚠️ Rerank Qwen: quota/rate limit", flush=True)
                return None
            resp.raise_for_status()
        text   = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_rerank_response(text, candidates)
        print(f"✅ Rerank Qwen — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except Exception as e:
        print(f"⚠️ Rerank Qwen KO: {str(e)[:120]}", flush=True)
        return None

async def _rerank_groq(extraction: dict, candidates: list) -> Optional[dict]:
    if not GROQ_API_KEY:
        return None
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(_candidates_for_prompt(candidates), ensure_ascii=False),
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
                    "max_tokens":  RERANK_MAX_OUTPUT_TOKENS,
                },
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
        text   = resp.json()["choices"][0]["message"]["content"].strip()
        result = _parse_rerank_response(text, candidates)
        print(f"✅ Rerank Groq — {result['meilleur_titre']} (score={result['score']})", flush=True)
        return result
    except Exception as e:
        print(f"⚠️ Rerank Groq KO: {str(e)[:120]}", flush=True)
        return None


def apply_quote_corroboration(result: dict, quote_candidate_ids: set) -> dict:
    """
    Si le candidat retenu par le rerank est également corroboré par une
    réplique exacte trouvée sur le web (signal indépendant du LLM,
    donc non sujet aux mêmes hallucinations), on booste le score de
    confiance de façon mesurée — jamais au-delà de 95, jamais une
    confiance "aveugle" à 100.
    """
    if not result or not quote_candidate_ids:
        return result
    if result.get("id") in quote_candidate_ids:
        old_score = result.get("score", 0)
        boosted = min(95, old_score + 15)
        if boosted > old_score:
            print(f" Corroboration réplique confirmée → score {old_score} → {boosted}", flush=True)
            result["score"] = boosted
            result["quote_corroborated"] = True
    return result
# ═══════════════════════════ POINT D'ENTRÉE ═══════════════════════

async def rerank(extraction: dict, candidates: list) -> dict:
    """
    Cascade :
      0. OpenRouter  → premier plan si activé
      1. Gemini      → fallback
      2. Qwen        → fallback
      3. Groq        → fallback
      4. Meilleur LLM sous seuil
      5. Match direct
      6. Popularité TMDB

    Important :
    Le rerank choisit toujours 1 meilleur résultat.
    Les 3-4 alternatives sont construites ensuite dans app.py à partir des
    autres candidats TMDB.
    """
    if not candidates:
        return {
            "meilleur_titre": "Inconnu",
            "id": None,
            "score": 0,
            "media_type": "movie",
        }

    if len(candidates) == 1:
        return _single_candidate_result(extraction, candidates[0])

    # ── 0. OpenRouter en premier ────────────────────────────────
    openrouter_result = await _rerank_openrouter(extraction, candidates)
    if openrouter_result and openrouter_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return openrouter_result
    if openrouter_result:
        print(
            f"⚠️ OpenRouter score faible ({openrouter_result['score']}) → tentative Gemini",
            flush=True,
        )

    # ── 1. Gemini Flash ─────────────────────────────────────────
    gemini_result = None
    if not GEMINI_RERANK_DISABLED:
        gemini_result = await _rerank_gemini(extraction, candidates)
        if gemini_result and gemini_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
            return gemini_result
        if gemini_result:
            print(
                f"⚠️ Gemini score faible ({gemini_result['score']}) → tentative Qwen",
                flush=True,
            )
    else:
        print("ℹ️ Gemini rerank désactivé (GEMINI_RERANK_DISABLED=true)", flush=True)

    # ── 2. Qwen ─────────────────────────────────────────────────
    qwen_result = await _rerank_qwen(extraction, candidates)
    if qwen_result and qwen_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return qwen_result
    if qwen_result:
        print(
            f"⚠️ Qwen score faible ({qwen_result['score']}) → tentative Groq",
            flush=True,
        )

    # ── 3. Groq ─────────────────────────────────────────────────
    groq_result = await _rerank_groq(extraction, candidates)
    if groq_result and groq_result.get("score", 0) >= GROQ_CONFIDENCE_THRESHOLD:
        return groq_result
    if groq_result:
        print(
            f"⚠️ Groq score faible ({groq_result['score']}) → aucun LLM n'a atteint le seuil",
            flush=True,
        )

    # ── 4. Meilleur LLM sous le seuil ───────────────────────────
    llm_results = [
        r for r in [
            openrouter_result,
            gemini_result,
            qwen_result,
            groq_result,
        ]
        if r is not None
    ]

    if llm_results:
        best_llm = max(llm_results, key=lambda r: r.get("score", 0))
        print(
            f"⚠️ Meilleur LLM sous seuil retenu : "
            f"{best_llm['meilleur_titre']} ({best_llm['score']})",
            flush=True,
        )
        return best_llm

    # ── 5. Match direct ─────────────────────────────────────────
    direct_result = _direct_match(extraction, candidates)
    if direct_result:
        print(
            f"⚠️ LLM tous KO → match direct "
            f"({direct_result['meilleur_titre']}, score={direct_result['score']})",
            flush=True,
        )
        return direct_result

    # ── 6. Popularité ───────────────────────────────────────────
    return _best_by_popularity(candidates)