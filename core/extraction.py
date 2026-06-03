"""
core/extraction.py — Extraction multimodale.

Cascade :
  1. Gemini vision → frames + OCR + transcript
  2. Fallback minimal → retour vide si Gemini échoue
"""
import traceback
import json
import os
import base64
import httpx

from core.prompts import EXTRACTION_PROMPT

# ── Clés API ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)

GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
]

TRANSCRIPT_THRESHOLD = 80

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
    # Chercher le JSON entre { }
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
        "source":             source,
    }


def _encode_image(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Gemini vision (frames + transcript + OCR)
# ════════════════════════════════════════════════════════════════
async def _extract_gemini_vision(frames: list, prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip Gemini", flush=True)
        return None

    parts = []
    for fp in frames[:6]:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({
                    "inline_data": {"mime_type": "image/jpeg", "data": b64}
                })

    if not parts:
        print("⚠️ Aucune frame valide pour Gemini", flush=True)

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

            raw      = resp.json()
            candidate = raw.get("candidates", [{}])[0]

            # Détecter blocage Gemini (safety filters)
            finish_reason = candidate.get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                print(
                    f"⚠️ Gemini ({model_name}) bloqué : finishReason={finish_reason}",
                    flush=True
                )
                continue

            text = (
                candidate
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()

            if not text:
                print(f"⚠️ Gemini ({model_name}) : réponse vide", flush=True)
                # Logger la réponse brute pour debug
                print(f"⚠️ Réponse brute : {str(raw)[:300]}", flush=True)
                continue

            print(f"📄 Gemini texte brut ({model_name}) : {text[:200]}", flush=True)

            text = _clean_json_fences(text)
            data = json.loads(text)
            data["source"] = "gemini_vision"
            print(f"✅ Gemini OK ({model_name}, {len(text)} chars)", flush=True)
            print(
                f"🔍 titres={data.get('titres_possibles')}, "
                f"desc={str(data.get('description_courte', ''))[:80]}",
                flush=True
            )
            return data

        except json.JSONDecodeError as e:
            print(f"⚠️ Gemini ({model_name}) : JSON invalide — {str(e)[:60]}", flush=True)
            print(f"⚠️ Texte reçu : {text[:300]}", flush=True)
            result = _minimal_fallback("gemini_partial")
            result["description_courte"] = text[:300] if "text" in locals() else ""
            return result
        except Exception as e:
            print(f"⚠️ Gemini KO ({model_name}): {str(e)[:300]}", flush=True)
            print(f"⚠️ Traceback: {traceback.format_exc()[:500]}", flush=True)
            continue

    return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
async def multimodal_extract(frames, ocr_text, transcript):
    ocr_text   = (ocr_text   or "").strip()
    transcript = (transcript or "").strip()

    combined = f"{transcript} {ocr_text}".strip()

    # Si pas de frames ET pas assez de texte → inutile d'appeler Gemini
    if not frames and len(combined) < TRANSCRIPT_THRESHOLD:
        print("⚠️ Pas assez de données → retour minimal", flush=True)
        result = _minimal_fallback("insufficient_data")
        result["description_courte"] = combined
        return result

    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text,
        transcript=transcript
    )

    # ── 1. Gemini vision (frames + OCR + transcript) ──────────────
    print("🔍 Gemini vision...", flush=True)
    result = await _extract_gemini_vision(frames, prompt)
    if result:
        return result

    # ── 2. Fallback minimal ───────────────────────────────────────
    print("⚠️ Gemini échoué → retour minimal", flush=True)
    result = _minimal_fallback("fallback")
    result["description_courte"] = combined[:300]
    return result