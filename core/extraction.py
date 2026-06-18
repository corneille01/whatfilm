"""
core/extraction.py — Extraction multimodale.

Cascade :
  1. Gemini 2.5 Flash vision → frames + OCR + transcript
  2. Gemini 2.5 Flash Lite   → fallback si Flash tronque
  3. Retour minimal si tout échoue

Fix v5 :
  - acteurs_certitude : nouveau champ JSON retourné par Gemini
  - Normalisation acteurs_certitude dans _call_gemini et _extract_gemini_url_direct

Fix v6 :
  - _try_parse_partial_json : récupère les champs utiles d'un JSON tronqué
  - Quand MAX_TOKENS détecté, tente le parse partiel avant de fallback
  - Si partiel contient titres/acteurs → utilisé directement sans appel Lite

Fix v7 :
  - is_ai_generated : détection contenu généré par IA (Sora, Runway, etc.)
  - Normalisé dans _call_gemini, _extract_gemini_url_direct et _minimal_fallback
"""
import json
import os
import re
import base64
import httpx
import asyncio

from core.prompts import EXTRACTION_PROMPT

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)

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


def _try_parse_partial_json(text: str) -> dict | None:
    """
    Tente d'extraire les champs déjà complets d'un JSON tronqué (MAX_TOKENS).
    Stratégie : regex champ par champ sur le texte brut.
    Retourne un dict partiel ou None si rien d'utile trouvé.
    """
    result = {}

    patterns = {
        "titres_possibles":   r'"titres_possibles"\s*:\s*(\[[^\]]*\])',
        "acteurs":            r'"acteurs"\s*:\s*(\[[^\]]*\])',
        "acteurs_certitude":  r'"acteurs_certitude"\s*:\s*(\[[^\]]*\])',
        "personnages":        r'"personnages"\s*:\s*(\[[^\]]*\])',
        "objets_importants":  r'"objets_importants"\s*:\s*(\[[^\]]*\])',
        "indices_visuels":    r'"indices_visuels"\s*:\s*(\[[^\]]*\])',
        "genre_apparent":     r'"genre_apparent"\s*:\s*"([^"]*)"',
        "langue_originale":   r'"langue_originale"\s*:\s*"([^"]*)"',
        "annee_estimee":      r'"annee_estimee"\s*:\s*(\d+|null)',
        "description_courte": r'"description_courte"\s*:\s*"([^"]*)"',
        "is_ai_generated":    r'"is_ai_generated"\s*:\s*(true|false)',
    }

    array_fields = {
        "titres_possibles", "acteurs", "acteurs_certitude",
        "personnages", "objets_importants", "indices_visuels",
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, text)
        if not m:
            continue
        raw = m.group(1)
        try:
            if field in array_fields:
                result[field] = json.loads(raw)
            elif field == "annee_estimee":
                result[field] = None if raw == "null" else int(raw)
            elif field == "is_ai_generated":
                result[field] = raw == "true"
            else:
                result[field] = raw
        except Exception:
            pass

    return result if result else None


def _minimal_fallback(source: str) -> dict:
    return {
        "titres_possibles":   [],
        "acteurs":            [],
        "acteurs_certitude":  [],
        "personnages":        [],
        "objets_importants":  [],
        "description_courte": "",
        "genre_apparent":     "",
        "annee_estimee":      None,
        "langue_originale":   "",
        "indices_visuels":    [],
        "is_ai_generated":    False,
        "source":             source,
    }


def _encode_image(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


def _normalize_acteurs_certitude(data: dict, default_certitude: int = 50) -> dict:
    """
    Aligne acteurs_certitude avec acteurs.
    Si Gemini oublie le champ ou retourne une liste de mauvaise taille,
    on complète avec default_certitude.
    """
    acteurs    = data.get("acteurs", []) or []
    certitudes = data.get("acteurs_certitude", []) or []

    while len(certitudes) < len(acteurs):
        certitudes.append(default_certitude)

    certitudes = certitudes[:len(acteurs)]
    certitudes = [
        int(c) if isinstance(c, (int, float)) else default_certitude
        for c in certitudes
    ]

    data["acteurs_certitude"] = certitudes
    return data


def _normalize_all_fields(data: dict, default_certitude: int = 50) -> dict:
    """
    Normalise tous les champs du dict retourné par Gemini :
    - setdefault pour les champs manquants
    - aligne acteurs_certitude avec acteurs
    - force is_ai_generated en booléen
    """
    data.setdefault("titres_possibles",   [])
    data.setdefault("acteurs",            [])
    data.setdefault("acteurs_certitude",  [])
    data.setdefault("personnages",        [])
    data.setdefault("objets_importants",  [])
    data.setdefault("description_courte", "")
    data.setdefault("genre_apparent",     "")
    data.setdefault("annee_estimee",      None)
    data.setdefault("langue_originale",   "")
    data.setdefault("indices_visuels",    [])
    data.setdefault("is_ai_generated",    False)

    # Forcer les types
    data["is_ai_generated"] = bool(data.get("is_ai_generated", False))

    # Aligner certitudes
    data = _normalize_acteurs_certitude(data, default_certitude)

    return data


# ════════════════════════════════════════════════════════════════
# OCR AUTOMATIQUE SUR LES FRAMES
# ════════════════════════════════════════════════════════════════

async def _ocr_frames(frames: list) -> str:
    """
    Passe les frames à Gemini Flash Lite pour extraire tout texte visible.
    Priorité aux caractères non-latins (JP/KO/ZH/AR).
    """
    if not GEMINI_API_KEY or not frames:
        return ""

    frames_to_ocr = frames[:3]
    parts = [
        {
            "text": (
                "Regarde ces images et extrais TOUT le texte visible à l'écran : "
                "titres, sous-titres, génériques, bannières, panneaux, logos, "
                "caractères japonais/coréens/chinois/arabes/cyrilliques. "
                "Transcris-les EXACTEMENT tels qu'écrits, y compris les caractères "
                "non-latins. Si tu vois un titre probable (sur une affiche, un générique, "
                "une bannière), indique-le en premier. "
                "Réponds UNIQUEMENT avec le texte extrait, sans explication. "
                "Si aucun texte visible, réponds 'AUCUN'."
            )
        }
    ]

    for fp in frames_to_ocr:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({
                    "inline_data": {"mime_type": "image/jpeg", "data": b64}
                })

    if len(parts) == 1:
        return ""

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature":     0.0,
            "maxOutputTokens": 300,
        }
    }

    try:
        lite_url = GEMINI_URLS[1]
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{lite_url}?key={GEMINI_API_KEY}", json=payload
            )
            resp.raise_for_status()

        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()

        if not text or text.upper() == "AUCUN":
            return ""

        print(f"🔤 OCR frames → {len(text)} chars : {text[:100]}", flush=True)
        return text[:500]

    except Exception as e:
        print(f"⚠️ OCR frames KO: {str(e)[:80]}", flush=True)
        return ""


# ════════════════════════════════════════════════════════════════
# APPEL GEMINI — paramétrable par modèle
# ════════════════════════════════════════════════════════════════

async def _call_gemini(
    url: str,
    parts: list,
    max_output_tokens: int = 3000,
) -> dict | None:
    """
    Appel générique Gemini. Retourne le dict parsé ou None.
    En cas de MAX_TOKENS, tente un parse partiel avant de retourner None.
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

        text = (
            candidate
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        ).strip()

        if not text:
            print(f"⚠️ Gemini ({model_name}) : réponse vide", flush=True)
            return None

        # ── Parse normal (pas de troncature) ─────────────────────
        if finish_reason != "MAX_TOKENS":
            clean = _clean_json_fences(text)
            try:
                data = json.loads(clean)
            except json.JSONDecodeError as e:
                print(
                    f"⚠️ Gemini ({model_name}) JSON invalide : {str(e)[:80]}",
                    flush=True
                )
                print(f"   Texte reçu : {text[:200]}", flush=True)
                return None

        else:
            # ── MAX_TOKENS : parse partiel ────────────────────────
            print(
                f"⚠️ Gemini ({model_name}) : réponse tronquée (MAX_TOKENS) "
                f"— tentative parse partiel",
                flush=True
            )
            # Essai 1 : le JSON est peut-être complet malgré MAX_TOKENS
            clean = _clean_json_fences(text)
            try:
                data = json.loads(clean)
                print(
                    f"✅ JSON complet malgré MAX_TOKENS ({model_name})",
                    flush=True
                )
            except json.JSONDecodeError:
                # Essai 2 : parse partiel champ par champ
                partial = _try_parse_partial_json(text)
                if partial and (
                    partial.get("titres_possibles") or partial.get("acteurs")
                ):
                    print(
                        f"✅ Parse partiel ({model_name}) — "
                        f"titres={partial.get('titres_possibles')}, "
                        f"acteurs={partial.get('acteurs')}, "
                        f"ai={partial.get('is_ai_generated', False)}",
                        flush=True
                    )
                    data = partial
                else:
                    print(
                        f"⚠️ Parse partiel ({model_name}) : rien d'utile "
                        f"→ fallback modèle suivant",
                        flush=True
                    )
                    return None

        # ── Normalisation complète ────────────────────────────────
        data["source"] = "gemini_vision"
        data = _normalize_all_fields(data, default_certitude=50)

        acteurs    = data.get("acteurs", [])
        certitudes = data.get("acteurs_certitude", [])
        titres     = data.get("titres_possibles", [])
        is_ai      = data.get("is_ai_generated", False)

        print(
            f"✅ Gemini OK ({model_name}, {len(text)} chars) — "
            f"titres={titres}, "
            f"acteurs={list(zip(acteurs, certitudes))}, "
            f"is_ai={is_ai}",
            flush=True
        )
        print(
            f"🔍 indices={data.get('indices_visuels')}, "
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

        if is_ai:
            print(
                f"🤖 Gemini ({model_name}) : contenu généré par IA détecté",
                flush=True
            )

        return data

    except Exception as e:
        print(f"⚠️ Gemini KO ({model_name}): {str(e)[:200]}", flush=True)
        return None


# ════════════════════════════════════════════════════════════════
# EXTRACTION YOUTUBE/URL DIRECTE (sans téléchargement)
# ════════════════════════════════════════════════════════════════
_YOUTUBE_DOMAINS = re.compile(r"youtube\.com|youtu\.be", re.IGNORECASE)
GEMINI_FILES_BASE = "https://generativelanguage.googleapis.com"


def _video_prompt() -> str:
    return EXTRACTION_PROMPT.format(
        ocr_text="",
        transcript=(
            "(Analyse cette vidéo directement. "
            "Extrais tous les dialogues audibles, textes visibles à l'écran, "
            "noms d'acteurs reconnaissables, et tout titre apparent. "
            "IMPORTANT pour les acteurs : ne liste un acteur QUE si tu le reconnais "
            "formellement avec une certitude ≥ 70%. Si le visage n'est pas clairement "
            "visible ou si tu n'es pas certain, laisse acteurs=[] et acteurs_certitude=[]. "
            "Détecte aussi si le contenu est généré par IA (is_ai_generated). "
            "Pour YouTube : utilise aussi les sous-titres automatiques si disponibles.)"
        ),
    )


async def _gemini_video_generate(file_uri: str, label: str, mime: str = "video/mp4") -> dict | None:
    """generateContent avec une partie vidéo (file_uri YouTube/URL OU fichier uploadé)."""
    if not GEMINI_API_KEY:
        return None
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": _video_prompt()},
            {"file_data": {"mime_type": mime, "file_uri": file_uri}},
        ]}],
        "generationConfig": {
            "temperature": 0.1, "maxOutputTokens": 3000,
            "responseMimeType": "application/json",
        },
    }
    print(f"🎬 Gemini {label}: {file_uri[:70]}", flush=True)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{GEMINI_URLS[0]}?key={GEMINI_API_KEY}", json=payload)
            resp.raise_for_status()
        candidate = resp.json().get("candidates", [{}])[0]
        if candidate.get("finishReason", "") in ("SAFETY", "RECITATION", "OTHER"):
            print(f"⚠️ Gemini {label} bloqué", flush=True)
            return None
        text = (candidate.get("content", {}).get("parts", [{}])[0].get("text", "")).strip()
        if not text:
            print(f"⚠️ Gemini {label}: réponse vide", flush=True)
            return None
        data = json.loads(_clean_json_fences(text))
        data["source"] = "gemini_url_direct"   # source fiable (vidéo entière)
        data = _normalize_all_fields(data, default_certitude=75)
        print(
            f"✅ Gemini {label} OK — titres={data.get('titres_possibles')}, "
            f"acteurs={data.get('acteurs')}, is_ai={data.get('is_ai_generated')}",
            flush=True,
        )
        return data
    except httpx.HTTPStatusError as e:
        print(f"⚠️ Gemini {label} HTTP {e.response.status_code}", flush=True)
        return None
    except json.JSONDecodeError as e:
        print(f"⚠️ Gemini {label} JSON KO: {e}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️ Gemini {label} KO: {str(e)[:160]}", flush=True)
        return None


async def _extract_gemini_url_direct(video_url: str) -> dict | None:
    """URL publique (YouTube, IG, FB…) → Gemini, sans téléchargement."""
    if not GEMINI_API_KEY:
        return None
    is_yt = bool(_YOUTUBE_DOMAINS.search(video_url))
    return await _gemini_video_generate(video_url, "YouTube direct" if is_yt else "URL directe")


async def _gemini_upload_file(path: str, mime: str = "video/mp4") -> dict | None:
    """Upload résumable d'un fichier local vers la Files API Gemini."""
    if not GEMINI_API_KEY or not os.path.exists(path):
        return None
    size = os.path.getsize(path)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            start = await client.post(
                f"{GEMINI_FILES_BASE}/upload/v1beta/files?key={GEMINI_API_KEY}",
                headers={
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(size),
                    "X-Goog-Upload-Header-Content-Type": mime,
                    "Content-Type": "application/json",
                },
                json={"file": {"display_name": os.path.basename(path)}},
            )
            start.raise_for_status()
            upload_url = start.headers.get("x-goog-upload-url")
            if not upload_url:
                print("⚠️ Files API: pas d'upload URL", flush=True)
                return None
            with open(path, "rb") as fh:
                content = fh.read()
            up = await client.post(
                upload_url,
                headers={
                    "Content-Length": str(size),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                content=content,
            )
            up.raise_for_status()
            return up.json().get("file") or None
    except Exception as e:
        print(f"⚠️ Files API upload KO: {str(e)[:160]}", flush=True)
        return None


async def _gemini_wait_active(name: str, max_attempts: int = 30) -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for _ in range(max_attempts):
                r = await client.get(f"{GEMINI_FILES_BASE}/v1beta/{name}?key={GEMINI_API_KEY}")
                r.raise_for_status()
                state = r.json().get("state", "")
                if state == "ACTIVE":
                    return True
                if state == "FAILED":
                    return False
                await asyncio.sleep(2)
    except Exception as e:
        print(f"⚠️ Files API poll KO: {str(e)[:120]}", flush=True)
    return False


async def _gemini_delete_file(name: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.delete(f"{GEMINI_FILES_BASE}/v1beta/{name}?key={GEMINI_API_KEY}")
    except Exception:
        pass


async def _extract_gemini_video_file(video_path: str) -> dict | None:
    """Fichier vidéo LOCAL (téléchargé OU uploadé) → Gemini via Files API."""
    if not GEMINI_API_KEY or not os.path.exists(video_path):
        return None
    info = await _gemini_upload_file(video_path, "video/mp4")
    if not info:
        return None
    name, uri, state = info.get("name"), info.get("uri"), info.get("state", "")
    if not uri:
        return None
    if state != "ACTIVE" and not await _gemini_wait_active(name):
        print("⚠️ Fichier Gemini jamais ACTIVE", flush=True)
        await _gemini_delete_file(name)
        return None
    result = await _gemini_video_generate(uri, "vidéo fichier")
    await _gemini_delete_file(name)
    return result


# Alias compat
async def _extract_gemini_youtube(youtube_url: str) -> dict | None:
    return await _extract_gemini_url_direct(youtube_url)

# ════════════════════════════════════════════════════════════════
# EXTRACTION PRINCIPALE (frames + OCR + transcript)
# ════════════════════════════════════════════════════════════════

async def _extract_gemini_vision(
    frames: list,
    ocr_text: str,
    transcript: str,
) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip Gemini", flush=True)
        return None

    effective_ocr = ocr_text.strip()
    if not effective_ocr and frames:
        print("🔤 OCR vide → tentative OCR automatique sur frames...", flush=True)
        effective_ocr = await _ocr_frames(frames)
        if effective_ocr:
            print(f"✅ OCR auto → {len(effective_ocr)} chars", flush=True)
        else:
            print("ℹ️  OCR auto → rien trouvé", flush=True)

    prompt = EXTRACTION_PROMPT.format(
        ocr_text=effective_ocr[:MAX_OCR_CHARS],
        transcript=transcript[:MAX_TRANSCRIPT_CHARS],
    )

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
                "aussi visuellement. "
                "RAPPEL : pour les acteurs, certitude ≥ 70% obligatoire. "
                "Si doute → acteurs=[] acteurs_certitude=[]. "
                "Évalue aussi is_ai_generated (2+ signaux IA → true). "
                "Si tu vois des caractères non-latins sur une bannière ou générique, "
                "transcris-les EXACTEMENT dans titres_possibles. "
                "Réponds UNIQUEMENT en JSON valide sur une seule ligne."
            )
        })

    # ── Tentative 1 : Flash ───────────────────────────────────────
    flash_url = GEMINI_URLS[0]
    result = await _call_gemini(flash_url, parts, max_output_tokens=3000)
    if result:
        return result

    # ── Tentative 2 : Flash avec 3 frames seulement ───────────────
    if len(frames) > 3:
        print("🔄 Retry Flash avec 3 frames seulement...", flush=True)
        parts_reduced = [parts[0]]
        count = 0
        for part in parts[1:]:
            if "inline_data" in part and count < 3:
                parts_reduced.append(part)
                count += 1
        if transcript:
            parts_reduced.append(parts[-1])

        result = await _call_gemini(flash_url, parts_reduced, max_output_tokens=3000)
        if result:
            return result

    # ── Tentative 3 : Flash Lite ──────────────────────────────────
    print("🔄 Fallback Flash Lite...", flush=True)
    lite_url = GEMINI_URLS[1]
    result = await _call_gemini(lite_url, parts, max_output_tokens=3000)
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