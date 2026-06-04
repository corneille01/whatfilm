"""
core/extraction.py — Extraction multimodale.

Cascade :
  1. Gemini 2.5 Flash vision → frames + OCR + transcript
  2. Gemini 2.5 Flash Lite   → fallback si Flash tronque
  3. Retour minimal si tout échoue

Fix v2 :
  - maxOutputTokens 1024 → 2048 (évite MAX_TOKENS avec 6 frames)
  - Lite utilisé uniquement en fallback, pas en égal
  - Log explicite quand acteurs vides
"""
import json
import os
import base64
import httpx

from core.prompts import EXTRACTION_PROMPT

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)

# Flash d'abord, Lite en fallback seulement
GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
]

TRANSCRIPT_THRESHOLD = 80
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
# APPEL GEMINI — paramétrable par modèle
# ════════════════════════════════════════════════════════════════
async def _call_gemini(
    url: str,
    parts: list,
    max_output_tokens: int = 2048,
) -> dict | None:
    """
    Appel générique Gemini. Retourne le dict parsé ou None.
    """
    model_name = url.split("/models/")[1].split(":")[0]

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature":      0.1,
            "maxOutputTokens":  max_output_tokens,
            "responseMimeType": "application/json",
        }
    }

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(
                f"{url}?key={GEMINI_API_KEY}", json=payload
            )
            resp.raise_for_status()

        raw       = resp.json()
        candidate = raw.get("candidates", [{}])[0]

        finish_reason = candidate.get("finishReason", "")
        if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
            print(f"⚠️ Gemini ({model_name}) bloqué : {finish_reason}", flush=True)
            return None

        if finish_reason == "MAX_TOKENS":
            # On log mais on tente quand même de parser ce qu'on a
            print(f"⚠️ Gemini ({model_name}) : réponse tronquée (MAX_TOKENS) "
                  f"— tentative de parse partiel", flush=True)

        text = (
            candidate
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()

        if not text:
            print(f"⚠️ Gemini ({model_name}) : réponse vide", flush=True)
            return None

        text = _clean_json_fences(text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"⚠️ Gemini ({model_name}) JSON invalide : {str(e)[:80]}",
                  flush=True)
            print(f"   Texte reçu : {text[:200]}", flush=True)
            return None

        # Normaliser les champs manquants
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

        # Log résultat
        acteurs = data.get("acteurs", [])
        titres  = data.get("titres_possibles", [])
        print(
            f"✅ Gemini OK ({model_name}, {len(text)} chars) — "
            f"acteurs={acteurs}, titres={titres}",
            flush=True
        )
        print(
            f"🔍 titres={titres}, "
            f"acteurs={acteurs}, "
            f"indices={data.get('indices_visuels')}, "
            f"desc={str(data.get('description_courte', ''))[:100]}",
            flush=True
        )

        if not acteurs:
            print(
                f"ℹ️  Gemini ({model_name}) : aucun acteur reconnu — "
                f"frames={len([p for p in payload['contents'][0]['parts'] if 'inline_data' in p])}, "
                f"transcript={len([p for p in payload['contents'][0]['parts'] if 'text' in p and len(p.get('text','')) > 100])} blocs texte",
                flush=True
            )

        return data

    except Exception as e:
        print(f"⚠️ Gemini KO ({model_name}): {str(e)[:200]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# EXTRACTION PRINCIPALE
# ════════════════════════════════════════════════════════════════
async def _extract_gemini_vision(
    frames: list,
    ocr_text: str,
    transcript: str,
) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip Gemini", flush=True)
        return None

    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text[:MAX_OCR_CHARS],
        transcript=transcript[:MAX_TRANSCRIPT_CHARS],
    )

    # Prompt en premier, puis frames, puis rappel de croisement
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

    if frames_added > 0 and transcript:
        parts.append({
            "text": (
                f"Tu as {frames_added} image(s) ci-dessus ET la transcription complète "
                f"({len(transcript)} chars) dans le prompt. "
                "Croise obligatoirement les deux : si tu reconnais un visage, "
                "cherche si un nom correspondant est mentionné dans la transcription. "
                "Si la transcription cite un titre ou un nom propre, vérifie si tu le vois "
                "aussi visuellement. Réponds UNIQUEMENT en JSON valide sur une seule ligne."
            )
        })

    # ── Tentative 1 : Flash avec maxOutputTokens=2048 ────────────
    flash_url  = GEMINI_URLS[0]
    result = await _call_gemini(flash_url, parts, max_output_tokens=2048)
    if result:
        return result

    # ── Tentative 2 : Flash avec moins de frames (3 au lieu de 6) ─
    # Si Flash échoue encore (ex: quota), réduire le payload
    if len(frames) > 3:
        print("🔄 Retry Flash avec 3 frames seulement...", flush=True)
        parts_reduced = [parts[0]]  # prompt
        count = 0
        for part in parts[1:]:
            if "inline_data" in part and count < 3:
                parts_reduced.append(part)
                count += 1
        if transcript:
            parts_reduced.append(parts[-1])  # rappel croisement

        result = await _call_gemini(flash_url, parts_reduced,
                                    max_output_tokens=2048)
        if result:
            return result

    # ── Tentative 3 : Flash Lite (fallback) ──────────────────────
    print("🔄 Fallback Flash Lite...", flush=True)
    lite_url = GEMINI_URLS[1]
    result = await _call_gemini(lite_url, parts, max_output_tokens=2048)
    if result:
        return result

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