"""
core/extraction.py — Extraction multimodale avec cascade complète.

Cascade :
  1. Vidéo entière uploadée → Gemini 2.5 Flash (Files API)
  2. Si échec → Qwen VL (DashScope international, SDK)
  3. Si échec → 6 frames extraites + OCR + transcript → Gemini vision (Flash/Lite)

Fonctions préservées :
  - Extraction YouTube/URL directe (_extract_gemini_url_direct)
  - Extraction frames + transcript (multimodal_extract) – toujours utilisable directement
  - Normalisation avancée des champs (acteurs_certitude, is_ai_generated, etc.)
  - Parsing partiel JSON tronqué
  - Upload résumable avec polling
"""

import json
import os
import re
import base64
import asyncio
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List

import httpx

# Configuration DashScope (international)
try:
    import dashscope
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"
    from dashscope import MultiModalConversation
    _DASHSCOPE_AVAILABLE = True
except ImportError:
    print("⚠️ Module 'dashscope' non installé → fallback Qwen VL désactivé", flush=True)
    MultiModalConversation = None
    _DASHSCOPE_AVAILABLE = False

from core.prompts import EXTRACTION_PROMPT

# ═══════════════ CONFIGURATION ═══════════════
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
]
GEMINI_FILES_BASE = "https://generativelanguage.googleapis.com"

TRANSCRIPT_THRESHOLD = 80
MAX_TRANSCRIPT_CHARS = 80000
MAX_OCR_CHARS = 3000

# ═══════════════ UTILITAIRES EXISTANTS ═══════════════
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
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text

def _try_parse_partial_json(text: str) -> Optional[Dict[str, Any]]:
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

def _encode_image(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

def _normalize_acteurs_certitude(data: dict, default_certitude: int = 50) -> dict:
    acteurs = data.get("acteurs", []) or []
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
    data["is_ai_generated"] = bool(data.get("is_ai_generated", False))
    data = _normalize_acteurs_certitude(data, default_certitude)
    return data

# ═══════════════ OCR AUTOMATIQUE ═══════════════
async def _ocr_frames(frames: list) -> str:
    if not GEMINI_API_KEY or not frames:
        return ""
    frames_to_ocr = frames[:3]
    parts = [{"text": (
        "Regarde ces images et extrais TOUT le texte visible à l'écran : "
        "titres, sous-titres, génériques, bannières, panneaux, logos, "
        "caractères japonais/coréens/chinois/arabes/cyrilliques. "
        "Transcris-les EXACTEMENT tels qu'écrits, y compris les caractères "
        "non-latins. Si tu vois un titre probable, indique-le en premier. "
        "Réponds UNIQUEMENT avec le texte extrait, sans explication. "
        "Si aucun texte visible, réponds 'AUCUN'."
    )}]
    for fp in frames_to_ocr:
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    if len(parts) == 1:
        return ""
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300}
    }
    try:
        lite_url = GEMINI_URLS[1]
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{lite_url}?key={GEMINI_API_KEY}", json=payload)
            resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text or text.upper() == "AUCUN":
            return ""
        print(f"🔤 OCR frames → {len(text)} chars : {text[:100]}", flush=True)
        return text[:500]
    except Exception as e:
        print(f"⚠️ OCR frames KO: {str(e)[:80]}", flush=True)
        return ""

# ═══════════════ APPEL GEMINI GÉNÉRIQUE ═══════════════
async def _call_gemini(url: str, parts: list, max_output_tokens: int = 3000) -> Optional[dict]:
    model_name = url.split("/models/")[1].split(":")[0]
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        }
    }
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(f"{url}?key={GEMINI_API_KEY}", json=payload)
            resp.raise_for_status()
        raw = resp.json()
        candidate = raw.get("candidates", [{}])[0]
        finish_reason = candidate.get("finishReason", "")
        if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
            print(f"⚠️ Gemini ({model_name}) bloqué : {finish_reason}", flush=True)
            return None
        text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            print(f"⚠️ Gemini ({model_name}) : réponse vide", flush=True)
            return None

        if finish_reason != "MAX_TOKENS":
            clean = _clean_json_fences(text)
            try:
                data = json.loads(clean)
            except json.JSONDecodeError:
                print(f"⚠️ Gemini ({model_name}) JSON invalide", flush=True)
                return None
        else:
            print(f"⚠️ Gemini ({model_name}) réponse tronquée (MAX_TOKENS) — tentative parse partiel", flush=True)
            clean = _clean_json_fences(text)
            try:
                data = json.loads(clean)
                print(f"✅ JSON complet malgré MAX_TOKENS ({model_name})", flush=True)
            except json.JSONDecodeError:
                partial = _try_parse_partial_json(text)
                if partial and (partial.get("titres_possibles") or partial.get("acteurs")):
                    print(f"✅ Parse partiel ({model_name}) — titres={partial.get('titres_possibles')}", flush=True)
                    data = partial
                else:
                    print(f"⚠️ Parse partiel ({model_name}) rien d'utile", flush=True)
                    return None

        data["source"] = "gemini_vision"
        data = _normalize_all_fields(data, default_certitude=50)
        acteurs = data.get("acteurs", [])
        certitudes = data.get("acteurs_certitude", [])
        titres = data.get("titres_possibles", [])
        is_ai = data.get("is_ai_generated", False)
        print(f"✅ Gemini OK ({model_name}) — titres={titres}, acteurs={list(zip(acteurs, certitudes))}, is_ai={is_ai}", flush=True)
        return data
    except Exception as e:
        print(f"⚠️ Gemini KO ({model_name}): {str(e)[:200]}", flush=True)
        return None

# ═══════════════ YOUTUBE / URL DIRECTE ═══════════════
_YOUTUBE_DOMAINS = re.compile(r"youtube\.com|youtu\.be", re.IGNORECASE)

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

async def _gemini_video_generate(file_uri: str, label: str, mime: str = "video/mp4") -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": _video_prompt()},
                {"file_data": {"mime_type": mime, "file_uri": file_uri}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        }
    }
    print(f"🎬 Gemini {label}: {file_uri[:70]}", flush=True)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{GEMINI_URLS[0]}?key={GEMINI_API_KEY}", json=payload)
            resp.raise_for_status()
        candidate = resp.json()["candidates"][0]
        text = candidate["content"]["parts"][0]["text"].strip()
        if not text:
            return None
        try:
            data = json.loads(_clean_json_fences(text))
        except json.JSONDecodeError:
            partial = _try_parse_partial_json(text)
            if not partial or not (partial.get("titres_possibles") or partial.get("acteurs")):
                return None
            data = partial
        data["source"] = "gemini_url_direct"
        return _normalize_all_fields(data, default_certitude=75)
    except Exception as e:
        print(f"❌ Gemini {label}: {e}", flush=True)
        return None

async def _extract_gemini_url_direct(video_url: str) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    is_yt = bool(_YOUTUBE_DOMAINS.search(video_url))
    return await _gemini_video_generate(video_url, "YouTube direct" if is_yt else "URL directe")

# ═══════════════ UPLOAD VIDÉO LOCAL + EXTRACTION ═══════════════
async def _gemini_upload_file(path: str, mime: str = "video/mp4") -> Optional[dict]:
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
            file_info = up.json().get("file") or {}
            return file_info
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

async def _extract_gemini_video_file(video_path: str) -> Optional[dict]:
    if not GEMINI_API_KEY or not os.path.exists(video_path):
        return None
    info = await _gemini_upload_file(video_path, "video/mp4")
    if not info:
        return None
    name = info.get("name")
    uri = info.get("uri")
    if not uri:
        return None
    if info.get("state") != "ACTIVE" and not await _gemini_wait_active(name):
        print("⚠️ Fichier jamais ACTIVE", flush=True)
        await _gemini_delete_file(name)
        return None
    result = await _gemini_video_generate(uri, "vidéo fichier")
    await _gemini_delete_file(name)
    return result

# ═══════════════ EXTRACTION FRAMES + OCR + TRANSCRIPT (existante) ═══════════════
async def _extract_gemini_vision(frames: list, ocr_text: str, transcript: str) -> Optional[dict]:
    if not GEMINI_API_KEY:
        return None
    effective_ocr = ocr_text.strip()
    if not effective_ocr and frames:
        effective_ocr = await _ocr_frames(frames)
        if effective_ocr:
            print(f"✅ OCR auto → {len(effective_ocr)} chars", flush=True)
        else:
            print("ℹ️ OCR auto → rien trouvé", flush=True)

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
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
                frames_added += 1
    if frames_added == 0:
        print("⚠️ Aucune frame valide", flush=True)
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

    # Cascade Flash → Flash réduit → Flash Lite
    flash_url = GEMINI_URLS[0]
    result = await _call_gemini(flash_url, parts, max_output_tokens=3000)
    if result:
        return result
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
    print("🔄 Fallback Flash Lite...", flush=True)
    lite_url = GEMINI_URLS[1]
    result = await _call_gemini(lite_url, parts, max_output_tokens=3000)
    return result

async def multimodal_extract(frames, ocr_text, transcript):
    ocr_text = (ocr_text or "").strip()
    transcript = (transcript or "").strip()
    combined = f"{transcript} {ocr_text}".strip()
    if not frames and len(combined) < TRANSCRIPT_THRESHOLD:
        return _minimal_fallback("insufficient_data")
    result = await _extract_gemini_vision(frames, ocr_text, transcript)
    if result:
        return result
    print("⚠️ Gemini échoué → retour minimal", flush=True)
    fallback = _minimal_fallback("fallback")
    fallback["description_courte"] = combined[:500]
    return fallback

# ═══════════════ FALLBACK QWEN VL (DashScope International) ═══════════════

async def _extract_qwen_vl(video_path: str) -> Optional[dict]:
    """
    Fallback Qwen VL via l'API DashScope internationale (SDK).
    Envoie la vidéo en base64 dans le contenu.
    """
    if not _DASHSCOPE_AVAILABLE:   # ← cette ligne doit exister
        return None
    if not os.environ.get("DASHSCOPE_API_KEY"):
        return None
    if not os.path.exists(video_path):
        return None

    try:
        with open(video_path, "rb") as f:
            video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode()
    except Exception as e:
        print(f"⚠️ Qwen VL – échec lecture vidéo : {e}", flush=True)
        return None

    prompt = EXTRACTION_PROMPT.format(
        ocr_text="",
        transcript=(
            "Analyse cette vidéo complète. Extrais tous les dialogues audibles, "
            "textes visibles, noms d'acteurs reconnaissables, titre apparent, etc."
        )
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"video": f"data:video/mp4;base64,{video_b64}"},
                {"text": prompt}
            ]
        }
    ]

    try:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor() as pool:
            response = await loop.run_in_executor(
                pool,
                lambda: MultiModalConversation.call(
                    model="qwen3-vl-plus",
                    messages=messages,
                    api_key=os.getenv("DASHSCOPE_API_KEY"),
                    stream=False,
                )
            )

        output = response.output
        if not output or not output.choices:
            print("⚠️ Qwen VL – pas de réponse", flush=True)
            return None

        text = output.choices[0].message.content[0]["text"]
        if not text:
            return None

        try:
            data = json.loads(_clean_json_fences(text))
        except json.JSONDecodeError:
            data = _try_parse_partial_json(text)

        if not data:
            print("⚠️ Qwen VL – JSON inexploitable", flush=True)
            return None

        data["source"] = "qwen_vl"
        data = _normalize_all_fields(data, default_certitude=75)
        print(f"✅ Qwen VL OK – titres={data.get('titres_possibles')}", flush=True)
        return data

    except Exception as e:
        print(f"⚠️ Qwen VL KO : {e}", flush=True)
        return None

# ═══════════════ EXTRACTION FRAMES (FFMPEG) ═══════════════
def _extract_frames(video_path: str, num_frames: int = 6) -> List[str]:
    """Extrait num_frames frames à intervalles réguliers avec ffmpeg."""
    if not os.path.exists(video_path):
        return []
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            capture_output=True, text=True, check=True
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        interval = duration / (num_frames + 1)
        tmpdir = tempfile.mkdtemp(prefix="frames_")
        frames = []
        for i in range(1, num_frames + 1):
            t = interval * i
            out_path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
            subprocess.run(
                ["ffmpeg", "-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path, "-y"],
                capture_output=True, check=True
            )
            if os.path.exists(out_path):
                frames.append(out_path)
        return frames
    except Exception as e:
        print(f"⚠️ Erreur extraction frames: {e}", flush=True)
        return []

# ═══════════════ NOUVEAU POINT D'ENTRÉE AVEC CASCADE ═══════════════

async def extract(
    video_path: str,
    transcript: str = "",
    ocr_text: str = "",
    frames: Optional[List[str]] = None
) -> dict:
    """
    Cascade complète :
      1. Vidéo entière → Gemini Files API
      2. Échec → Qwen VL (DashScope)
      3. Échec → 6 frames + OCR + Gemini vision
    """
    # 1. Gemini vidéo directe
    print(f"🎬 Tentative Gemini vidéo : {video_path}", flush=True)
    result = await _extract_gemini_video_file(video_path)
    if result:
        return result

    # 2. Qwen VL (DashScope)
    print("🔄 Fallback Qwen VL...", flush=True)
    result = await _extract_qwen_vl(video_path)
    if result:
        return result

    # 3. Frames (6 extraites automatiquement si non fournies)
    print("🔄 Fallback frames + Gemini vision...", flush=True)
    if not frames:
        frames = _extract_frames(video_path, num_frames=6)
        if not frames:
            return _minimal_fallback("no_frames")
    if not ocr_text.strip():
        print("🔤 OCR auto sur frames extraites", flush=True)
        ocr_text = await _ocr_frames(frames)
    return await multimodal_extract(frames, ocr_text, transcript)


# Alias pour compatibilité
async def _extract_gemini_youtube(url: str) -> Optional[dict]:
    return await _extract_gemini_url_direct(url)