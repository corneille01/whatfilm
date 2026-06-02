"""
core/extraction.py — Extraction multimodale avec logique transcript-first.

Cascade anti-coût (objectif : 0€ jusqu'à ~1M req/mois) :

  0. Regex/heuristique  → si titre trouvé directement (~10% des cas, 0 API call)
  1. Groq Llama texte   → transcript présent (~70% des cas, gratuit)
  2. Gemini vision      → analyse visuelle des frames (~20% des cas, gratuit <45K/mois)
  3. Retour minimal     → pipeline continue via TMDB texte

Le reranker (core/reranker.py) gère la sélection finale.
"""

import re
import json
import os
import base64
import httpx

from core.prompts import EXTRACTION_PROMPT

# ── Clés API ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)  # ← ici
print(f"🔑 GROQ_API_KEY présente: {bool(GROQ_API_KEY)}", flush=True)  # ← ici

GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-001:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-001:generateContent",
]
GROQ_TEXT_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

TRANSCRIPT_THRESHOLD = 80


# ════════════════════════════════════════════════════════════════
# NIVEAU 0 — Regex (0 API call)
# ════════════════════════════════════════════════════════════════
_YEAR_PATTERN = re.compile(r"\b(19[5-9]\d|20[0-3]\d)\b")
_QUOTED_TITLE = re.compile(
    r'[«»"\u201c\u201d\u201e\u2039\u203a]'
    r'([^\u00ab\u00bb"\u201c\u201d\u201e\u2039\u203a]{3,60})'
    r'[«»"\u201c\u201d\u201e\u2039\u203a]'
)
_ACTOR_PREFIXES = re.compile(
    r"(?:avec|starring|avec les acteurs|feat(?:uring)?\.?)\s+"
    r"([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){0,2})",
    re.IGNORECASE
)
_CAPS_TITLE = re.compile(
    r"(?:[A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ'\-]{1,20}\s+){1,5}"
    r"[A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ'\-]{1,20}"
)


def _regex_extract(ocr_text: str, transcript: str) -> dict | None:
    combined = f"{transcript} {ocr_text}".strip()
    if len(combined) < TRANSCRIPT_THRESHOLD:
        return None

    years  = _YEAR_PATTERN.findall(combined)
    quotes = _QUOTED_TITLE.findall(combined)
    actors = _ACTOR_PREFIXES.findall(combined)
    caps   = _CAPS_TITLE.findall(ocr_text) if ocr_text else []

    titres_possibles = list(dict.fromkeys(quotes + caps))[:5]

    if not titres_possibles and not actors and not years:
        return None

    print(
        f"✅ Extraction regex — titres: {titres_possibles[:2]}, "
        f"acteurs: {actors[:2]}, années: {years[:1]}",
        flush=True
    )
    return {
        "titres_possibles":   titres_possibles,
        "acteurs":            actors[:4],
        "personnages":        [],
        "objets_importants":  [],
        "description_courte": combined[:300],
        "genre_apparent":     "",
        "annee_estimee":      years[0] if years else None,
        "langue_originale":   "",
        "source":             "regex",
    }


# ════════════════════════════════════════════════════════════════
# UTILITAIRES
# ════════════════════════════════════════════════════════════════
def _clean_json_fences(text: str) -> str:
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _minimal_fallback(source: str) -> dict:
    return {
        "titres_possibles":   [],
        "acteurs":            [],
        "personnages":        [],
        "objets_importants":  [],
        "description_courte": "",
        "genre_apparent":     "",
        "annee_estimee":      None,
        "langue_originale":   "",
        "source":             source,
    }


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Groq Llama texte (sans vision)
# ════════════════════════════════════════════════════════════════
async def _extract_groq_text(prompt: str) -> dict | None:
    if not GROQ_API_KEY:
        return None

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
                                "Tu es un expert en cinéma et séries TV. "
                                "Réponds UNIQUEMENT en JSON valide, sans markdown, "
                                "sans texte avant ou après."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            resp.raise_for_status()

        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = _clean_json_fences(text)
        data = json.loads(text)
        data["source"] = "groq_text"
        print(f"✅ Groq texte OK ({len(text)} chars)", flush=True)
        return data

    except json.JSONDecodeError:
        result = _minimal_fallback("groq_text_partial")
        result["description_courte"] = text[:300] if "text" in locals() else ""
        return result
    except Exception as e:
        print(f"⚠️ Groq texte KO: {str(e)[:120]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# NIVEAU 2 — Gemini vision (frames + texte, dernier recours)
# ════════════════════════════════════════════════════════════════
def _encode_image(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


async def _extract_gemini_vision(frames: list, prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip vision", flush=True)
        return None

    parts = []
    for fp in frames[:4]:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({
                    "inline_data": {"mime_type": "image/jpeg", "data": b64}
                })

    if not parts:
        return None

    parts.append({"text": prompt})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        }
    }

    for url in GEMINI_URLS:
        model_name = url.split("/models/")[1].split(":")[0]
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}?key={GEMINI_API_KEY}", json=payload
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
                continue

            text = _clean_json_fences(text)
            data = json.loads(text)
            data["source"] = "gemini_vision"
            print(f"✅ Gemini vision OK ({model_name}, {len(text)} chars)", flush=True)
            return data

        except json.JSONDecodeError:
            result = _minimal_fallback("gemini_partial")
            result["description_courte"] = text[:300] if "text" in locals() else ""
            return result
        except Exception as e:
            print(f"⚠️ Gemini KO ({model_name}): {str(e)[:120]}", flush=True)
            continue

    return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
async def multimodal_extract(frames, ocr_text, transcript):
    ocr_text   = (ocr_text   or "").strip()
    transcript = (transcript or "").strip()

    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text,
        transcript=transcript
    )

    # ── 0. Regex — uniquement si titre trouvé directement ────────
    result = _regex_extract(ocr_text, transcript)
    if result and result.get("titres_possibles"):
        print(f"✅ Regex suffisante — titres trouvés directement", flush=True)
        return result

    # ── 1. Groq texte (toujours si transcript ou ocr présent) ────
    if ocr_text or transcript:
        print("🔍 Groq texte...", flush=True)
        result = await _extract_groq_text(prompt)
        if result:
            has_title  = bool(result.get("titres_possibles"))
            has_actors = bool(result.get("acteurs"))
            print(
                f"🔍 EXTRACTION Groq: titres={result.get('titres_possibles')}, "
                f"acteurs={result.get('acteurs')}, "
                f"desc={result.get('description_courte','')[:80]}",
                flush=True
            )
            # Si Groq a trouvé des titres ou acteurs → suffisant
            if has_title or has_actors:
                return result
            # Sinon on garde le résultat Groq comme base
            # mais on tente Gemini vision en complément
            groq_result = result
        else:
            groq_result = None
    else:
        groq_result = None

    # ── 2. Gemini vision (si Groq n'a pas trouvé de titre/acteur) ─
    if frames:
        print("🔍 Gemini vision...", flush=True)
        vision_result = await _extract_gemini_vision(frames, prompt)
        if vision_result:
            has_title  = bool(vision_result.get("titres_possibles"))
            has_actors = bool(vision_result.get("acteurs"))
            print(
                f"🔍 EXTRACTION Gemini: titres={vision_result.get('titres_possibles')}, "
                f"acteurs={vision_result.get('acteurs')}",
                flush=True
            )
            if has_title or has_actors:
                # Gemini a trouvé quelque chose — fusionne avec Groq si dispo
                if groq_result:
                    vision_result["description_courte"] = (
                        vision_result.get("description_courte")
                        or groq_result.get("description_courte", "")
                    )
                    vision_result["genre_apparent"] = (
                        vision_result.get("genre_apparent")
                        or groq_result.get("genre_apparent", "")
                    )
                    vision_result["annee_estimee"] = (
                        vision_result.get("annee_estimee")
                        or groq_result.get("annee_estimee")
                    )
                return vision_result

    # ── 3. Retour Groq si dispo (même sans titre) ─────────────────
    if groq_result:
        print("⚠️ Aucun titre trouvé — retour Groq partiel", flush=True)
        return groq_result

    # ── 4. Retour minimal ─────────────────────────────────────────
    print("⚠️ Extraction totalement échouée → retour minimal", flush=True)
    combined = f"{transcript} {ocr_text}".strip()
    result = _minimal_fallback("fallback")
    result["description_courte"] = combined[:300]
    return result