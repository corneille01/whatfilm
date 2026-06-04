"""
core/extraction.py — Extraction multimodale.

Cascade :
  1. Gemini vision → frames + OCR + transcript (croisement actif)
  2. Fallback minimal si Gemini échoue
"""
import traceback
import json
import os
import base64
import httpx

from core.prompts import EXTRACTION_PROMPT

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)

GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
]

TRANSCRIPT_THRESHOLD = 80

# Limite haute de transcription envoyée à Gemini.
# 1375 chars ≈ 340 tokens — on envoie TOUT, pas de troncature.
# Gemini 2.5 Flash supporte 1M tokens, il n'y a aucune raison de couper.
MAX_TRANSCRIPT_CHARS = 8000
MAX_OCR_CHARS        = 3000


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
        "indices_visuels":    [],
        "source":             source,
    }


def _encode_image(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Gemini vision
# ════════════════════════════════════════════════════════════════
async def _extract_gemini_vision(
    frames: list,
    ocr_text: str,
    transcript: str,
) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip Gemini", flush=True)
        return None

    # ── Construction du prompt avec transcription COMPLÈTE ───────
    # On ne tronque PAS la transcription — Gemini doit la lire en entier
    # pour croiser noms cités / dialogues avec ce qu'il voit sur les frames.
    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text[:MAX_OCR_CHARS],
        transcript=transcript[:MAX_TRANSCRIPT_CHARS],
    )

    # ── Parts : d'abord le texte d'instruction, puis les frames ──
    # On met le prompt EN PREMIER pour que Gemini l'ait en tête
    # quand il analyse chaque image. Ordre important pour l'attention.
    parts = [{"text": prompt}]

    frames_added = 0
    for fp in frames[:6]:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({
                    "inline_data": {"mime_type": "image/jpeg", "data": b64}
                })
                frames_added += 1

    if frames_added == 0:
        print("⚠️ Aucune frame valide pour Gemini", flush=True)

    # Message final : rappel explicite du croisement vision+transcription
    if frames_added > 0 and transcript:
        parts.append({
            "text": (
                f"Tu as {frames_added} image(s) ci-dessus ET la transcription complète "
                f"({len(transcript)} chars) dans le prompt. "
                "Croise obligatoirement les deux : si tu reconnais un visage sur une image, cherche si un nom correspondant est mentionné dans la transcription texte. Si la transcription cite un titre ou un nom propre, vérifie si tu le vois aussi visuellement. Réponds UNIQUEMENT en JSON valide sur une seule ligne."
                "cherche si un nom correspondant est mentionné dans la transcription. "
                "Si la transcription cite un titre ou un nom propre, vérifie si tu le vois "
                "aussi visuellement. Réponds UNIQUEMENT en JSON valide sur une seule ligne."
            )
        })

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature":      0.1,   # plus déterministe pour l'extraction
            "maxOutputTokens":  1024,  # suffisant pour le JSON d'extraction
            "responseMimeType": "application/json",
        }
    }

    for url in GEMINI_URLS:
        model_name = url.split("/models/")[1].split(":")[0]
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                resp = await client.post(
                    f"{url}?key={GEMINI_API_KEY}", json=payload
                )
                resp.raise_for_status()

            raw       = resp.json()
            candidate = raw.get("candidates", [{}])[0]

            finish_reason = candidate.get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                print(f"⚠️ Gemini ({model_name}) bloqué : {finish_reason}", flush=True)
                continue
            if finish_reason == "MAX_TOKENS":
                print(f"⚠️ Gemini ({model_name}) : réponse tronquée (MAX_TOKENS)", flush=True)

            text = (
                candidate
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()

            if not text:
                print(f"⚠️ Gemini ({model_name}) : réponse vide — {str(raw)[:200]}", flush=True)
                continue

            text = _clean_json_fences(text)

            try:
                data = json.loads(text)
                data["source"] = "gemini_vision"
                data.setdefault("titres_possibles",   [])
                data.setdefault("acteurs",            [])
                data.setdefault("personnages",        [])
                data.setdefault("objets_importants",  [])
                data.setdefault("description_courte", "")
                data.setdefault("genre_apparent",     "")
                data.setdefault("annee_estimee",      None)
                data.setdefault("langue_originale",   "")
                data.setdefault("indices_visuels",    [])

                print(
                    f"✅ Gemini OK ({model_name}, JSON {len(text)} chars, "
                    f"transcript {len(transcript)} chars envoyés)",
                    flush=True
                )
                print(
                    f"🔍 titres={data.get('titres_possibles')}, "
                    f"acteurs={data.get('acteurs')}, "
                    f"indices={data.get('indices_visuels')}, "
                    f"desc={str(data.get('description_courte', ''))[:100]}",
                    flush=True
                )
                return data

            except json.JSONDecodeError as e:
                print(f"⚠️ Gemini ({model_name}) JSON invalide — {str(e)[:60]}", flush=True)
                print(f"⚠️ Texte reçu : {text[:300]}", flush=True)
                continue

        except Exception as e:
            print(f"⚠️ Gemini KO ({model_name}): {str(e)[:200]}", flush=True)
            continue

    return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
async def multimodal_extract(frames, ocr_text, transcript):
    ocr_text   = (ocr_text   or "").strip()
    transcript = (transcript or "").strip()
    combined   = f"{transcript} {ocr_text}".strip()

    if not frames and len(combined) < TRANSCRIPT_THRESHOLD:
        print("⚠️ Pas assez de données → retour minimal", flush=True)
        result = _minimal_fallback("insufficient_data")
        result["description_courte"] = combined
        return result

    print(
        f"🔍 Gemini vision ({len(frames)} frames, "
        f"transcript={len(transcript)}c, ocr={len(ocr_text)}c)...",
        flush=True
    )
    result = await _extract_gemini_vision(frames, ocr_text, transcript)
    if result:
        return result

    print("⚠️ Gemini échoué → retour minimal", flush=True)
    result = _minimal_fallback("fallback")
    result["description_courte"] = combined[:500]
    return result