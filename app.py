import os
# ── Fix crash glibc getaddrinfo (rfc3484_sort) sur résolution DNS mixte IPv4/IPv6 ──
# Cf. logs Render : "Fatal glibc error: getaddrinfo.c:1642 (rfc3484_sort)" → SIGABRT
# du worker entier. On force la résolution DNS en IPv4 uniquement pour tous les
# clients HTTP (httpx) du process.
import socket
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return results if results else _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo



import uuid
import shutil
import subprocess
import traceback
import base64
import time
import asyncio
import re

import httpx

from core.embeddings_engine import check_known_film, store_film_signature
from core.quote_search import find_quote_corroboration
from core.feedback import get_correction_for_extraction, save_extraction_snapshot


from core.confidence import make_opinion, rank_opinions
from core.feedback import save_candidates_snapshot, submit_feedback
from core import extraction
from routes_filming import router as filming_router
from typing import Optional
from contextlib import asynccontextmanager
from collections import defaultdict
from storage.cache_engine.lock_manager import acquire_lock, release_lock
from storage.cache_engine.hash_utils import key_content  

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
    JSONResponse,
)
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.web_search import should_trigger_web_fallback, web_search_fallback
from core.wikidata import wikidata_search_candidates, should_trigger_wikidata, get_wikidata_enrichment, get_filming_locations
from core import filming_catalogue
from core.web_enrichment import (
    light_web_enrich_extraction,
    result_supported_by_web_light,
)


from vision.scene_detection import extract_keyframes
from vision.universal_downloader import download_video
from vision.ocr_engine import extract_text_from_images, start_loading
from vision.whisper_engine import transcribe

from core.extraction import multimodal_extract
from core.retrieval import build_candidates_from_actors, run_cascade_search
from data.tmdb import (
    search_candidates, search_tv_candidates,
    get_movie_details, get_tv_details,
    discover_by_genre, get_trending, get_season_details,
)

from data.fake_detector import detect_fake
from core.reranker import rerank, apply_quote_corroboration 
from storage.cache import (
    get_cache, get_cache_by_content, get_cache_by_film,
    get_cache_by_title, set_cache, purge_expired, cache_stats, cache_get_generic, cache_set_generic, 
)


# ════════════════════════════════════════════════════════════════
# NORMALISATION D'URL
# ════════════════════════════════════════════════════════════════
_TRACKING_PARAMS = {
    "_r", "_t", "s", "t", "utm_source", "utm_medium", "utm_campaign",
    "utm_content", "utm_term", "fbclid", "igshid", "ref",
    "is_from_webapp", "is_copy_url", "sender_device", "q", "is",
}



# ── Mapping langue → région (complet) ────────────────────────────
def _get_region_from_lang(lang: str) -> str:
    """Retourne le code pays ISO 3166-1 alpha-2 à partir de la langue du navigateur."""
    if not lang:
        return "US"
    lang = lang.lower()
    
    # Mapping étendu (identique au frontend)
    map_region = {
        'fr': 'FR', 'fr-fr': 'FR', 'fr-be': 'BE', 'fr-ca': 'CA', 'fr-ch': 'CH',
        'en': 'US', 'en-us': 'US', 'en-gb': 'GB', 'en-ca': 'CA', 'en-au': 'AU',
        'es': 'ES', 'es-es': 'ES', 'es-mx': 'MX', 'es-ar': 'AR',
        'de': 'DE', 'de-de': 'DE', 'de-at': 'AT', 'de-ch': 'CH',
        'it': 'IT', 'it-it': 'IT',
        'pt': 'BR', 'pt-br': 'BR', 'pt-pt': 'PT',
        'nl': 'NL', 'nl-nl': 'NL', 'nl-be': 'BE',
        'pl': 'PL', 'ru': 'RU', 'ja': 'JP', 'ko': 'KR',
        'zh': 'CN', 'zh-cn': 'CN', 'zh-tw': 'TW',
        'ar': 'AE', 'he': 'IL', 'tr': 'TR',
        'sv': 'SE', 'da': 'DK', 'no': 'NO', 'fi': 'FI'
    }
    return map_region.get(lang, map_region.get(lang.split('-')[0], 'US'))

def normalize_url(url: str) -> str:
    url = url.strip()
    if "?" not in url:
        return url
    base, qs = url.split("?", 1)
    kept = [
        part for part in qs.split("&")
        if "=" in part and part.split("=")[0] not in _TRACKING_PARAMS
    ]
    return base + ("?" + "&".join(kept) if kept else "")

# ════════════════════════════════════════════════════════════════
# DÉTECTION DE PLATEFORME
# ════════════════════════════════════════════════════════════════
SUPPORTED_PLATFORMS = re.compile(
    r"(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com"
    r"|instagram\.com|youtube\.com|youtu\.be"
    r"|twitter\.com|x\.com"
    r"|facebook\.com|fb\.watch"
    r"|dailymotion\.com|dai\.ly"
    r"|bilibili\.com"
    r"|snapchat\.com"
    r"|pinterest\.|pin\.it"
    r"|vimeo\.com"
    r"|twitch\.tv"
    r"|reddit\.com|redd\.it"
    r"|linkedin\.com)",
    re.IGNORECASE
)

def detect_platform(url: str) -> str:
    patterns = {
        "tiktok":      r"tiktok\.com|vm\.tiktok|vt\.tiktok",
        "instagram":   r"instagram\.com",
        "youtube":     r"youtube\.com|youtu\.be",
        "twitter":     r"twitter\.com|x\.com",
        "facebook":    r"facebook\.com|fb\.watch",
        "dailymotion": r"dailymotion\.com|dai\.ly",
        "bilibili":    r"bilibili\.com",
        "snapchat":    r"snapchat\.com",
        "vimeo":       r"vimeo\.com",
        "reddit":      r"reddit\.com|redd\.it",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, url, re.IGNORECASE):
            return name
    return "unknown"

async def _resolve_short_url(url: str) -> str:
    short_domains = r"bit\.ly|t\.co|tinyurl\.com|ow\.ly|buff\.ly|short\.io|lnk\.to"
    if not re.search(short_domains, url, re.IGNORECASE):
        return url
    try:
        import httpx
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            resp = await client.head(url)
            resolved = str(resp.url)
            print(f"🔗 URL résolue: {url[:40]} → {resolved[:60]}", flush=True)
            return resolved
    except Exception as e:
        
        return url

# ════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════
MAX_VIDEO_SECONDS = 120
GEMINI_MAX_SECONDS = 60
MAX_FILE_SIZE_MB  = 50

# Mode Shazam : afficher plusieurs possibilités si le résultat n'est pas ultra sûr
SHOULD_SHOW_ALTERNATIVES_BELOW = 88
ALTERNATIVES_CLOSE_GAP = 12

# ── RATE LIMITING ────────────────────────────────────────────────
_ip_minute: dict = defaultdict(list)
_ip_day:    dict = defaultdict(list)

RATE_PER_MINUTE = 10
RATE_PER_DAY    = 100

def _check_rate_limit(ip: str) -> Optional[dict]:
    now = time.time()
    _ip_minute[ip] = [t for t in _ip_minute[ip] if now - t < 60]
    _ip_day[ip]    = [t for t in _ip_day[ip]    if now - t < 86400]
    if len(_ip_minute[ip]) >= RATE_PER_MINUTE:
        return {"status": "error", "code": "rate_limited",
                "message": "Trop de requêtes. Attendez une minute avant de réessayer."}
    if len(_ip_day[ip]) >= RATE_PER_DAY:
        return {"status": "error", "code": "rate_limited_daily",
                "message": "Limite journalière atteinte. Revenez demain."}
    _ip_minute[ip].append(now)
    _ip_day[ip].append(now)
    return None



def _get_client_ip(request: Request) -> str:
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        val = request.headers.get(header, "")
        if val:
            return val.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ════════════════════════════════════════════════════════════════
# SESSIONS
# ════════════════════════════════════════════════════════════════
sessions:       dict = {}
SESSION_TIMEOUT: int = 300

_dl_sessions:      dict = {}
DL_SESSION_TIMEOUT: int = 600

async def cleanup_sessions():
    while True:
        now = time.time()
        expired = [sid for sid, s in list(sessions.items())
                   if now - s["timestamp"] > SESSION_TIMEOUT]
        for sid in expired:
            s = sessions.pop(sid, None)
            if s:
                for key in ("video_path", "audio_path", "frame_dir"):
                    p = s.get(key)
                    if p and os.path.exists(p):
                        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

        expired_dl = [sid for sid, s in list(_dl_sessions.items())
                      if now - s.get("timestamp", 0) > DL_SESSION_TIMEOUT]
        for sid in expired_dl:
            s = _dl_sessions.pop(sid, None)
            if s:
                for key in ("video_path", "audio_path", "frame_dir"):
                    p = s.get(key)
                    if p and os.path.exists(p):
                        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

        await asyncio.sleep(60)

async def purge_cache_loop():
    while True:
        await asyncio.sleep(3600)
        purge_expired()


# ── À INSÉRER dans le bloc lifespan de main.py, AVANT le yield ──
# Remplace le lifespan existant par celui-ci :

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from storage.cache import purge_by_code
        purged = purge_by_code("video_private")
        if purged:
            print(f"🧹 Cache empoisonné purgé: {purged} entrée(s) video_private", flush=True)
    except Exception as e:
        print(f"⚠️ Purge cache démarrage: {e}", flush=True)

    asyncio.create_task(cleanup_sessions())
    asyncio.create_task(purge_cache_loop())
    asyncio.create_task(filming_catalogue.ensure_catalogue_loaded())
    start_loading()

    # ── Redis keepalive (évite "Connection closed by server" sur Render free tier) ──
    async def _redis_keepalive():
        while True:
            await asyncio.sleep(50)  # toutes les 50s, avant le timeout serveur
            try:
                from storage.cache_engine.redis_client import get_redis
                r = get_redis()
                if r:
                    r.ping()
            except Exception:
                pass

    asyncio.create_task(_redis_keepalive())
    yield

app = FastAPI(title="Pelify", lifespan=lifespan)
app.include_router(filming_router)
from poi_proxy import router as poi_router
app.include_router(poi_router)

# ════════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT PUBLIC (page d'accueil) — indépendant du pipeline d'identification
# ════════════════════════════════════════════════════════════════
import yt_dlp
from starlette.background import BackgroundTask

MAX_DOWNLOAD_MB = 300  # garde-fou bande passante/disque Render


class DownloadFormatsRequest(BaseModel):
    url: str


@app.post("/download/formats")
async def download_formats(req: DownloadFormatsRequest, request: Request):
    ip = _get_client_ip(request)
    rate_err = _check_rate_limit(ip)
    if rate_err:
        return rate_err

    url = normalize_url(await _resolve_short_url(req.url.strip()))

    def _extract():
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
    except Exception:
        return {"status": "error", "code": "extract_failed",
                "message": "Impossible de lire ce lien. Vérifiez qu'il est public et valide."}

    formats, seen = [], set()
    for f in info.get("formats", []):
        if f.get("vcodec") == "none" and f.get("acodec") == "none":
            continue
        fid = f.get("format_id")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        is_audio_only = f.get("vcodec") == "none"
        label = (
            f"Audio {f.get('abr') or '?'}kbps ({f.get('ext')})" if is_audio_only
            else f"{f.get('height', '?')}p {f.get('ext')}"
        )
        formats.append({
            "format_id": fid,
            "label": label,
            "is_audio_only": is_audio_only,
            "filesize_approx": f.get("filesize") or f.get("filesize_approx"),
        })

    return {
        "status": "ok",
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "formats": formats,
    }


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    audio_only: bool = False


@app.post("/download")
async def download_file(req: DownloadRequest, request: Request):
    ip = _get_client_ip(request)
    rate_err = _check_rate_limit(ip)
    if rate_err:
        return rate_err

    url = normalize_url(await _resolve_short_url(req.url.strip()))
    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    out_template = f"temp/dl_{uid}.%(ext)s"

    fmt_selector = (
        req.format_id if req.audio_only
        else ("bestvideo+bestaudio/best" if req.format_id == "best"
              else f"{req.format_id}+bestaudio/best")
    )
    ydl_opts = {
        "format": fmt_selector,
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
    }
    if not req.audio_only:
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            return os.path.splitext(path)[0] + ".mp3" if req.audio_only else path

    try:
        final_path = await asyncio.to_thread(_download)
    except Exception:
        return {"status": "error", "code": "download_failed",
                "message": "Le téléchargement a échoué. Le lien est peut-être privé ou expiré."}

    if not os.path.exists(final_path):
        return {"status": "error", "code": "file_missing",
                "message": "Fichier introuvable après téléchargement."}

    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    if size_mb > MAX_DOWNLOAD_MB:
        os.remove(final_path)
        return {"status": "error", "code": "too_large",
                "message": f"Fichier trop volumineux ({size_mb:.0f} Mo, max {MAX_DOWNLOAD_MB} Mo)."}

    return FileResponse(
        final_path,
        filename=os.path.basename(final_path),
        background=BackgroundTask(lambda: os.path.exists(final_path) and os.remove(final_path)),
    )

_analysis_semaphore = asyncio.Semaphore(
    int(os.environ.get("ANALYSIS_MAX_CONCURRENT", "1"))
)


@app.middleware("http")
async def render_head_fix(request: Request, call_next):
    if request.method == "HEAD":
        return Response(status_code=200)
    return await call_next(request)


@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)

    path = request.url.path

    static_exts = (
        ".js",
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".svg",
        ".ico",
        ".woff2",
        ".webmanifest"
    )

    if path.startswith("/frontend/") and path.endswith(static_exts):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

    elif path in {"/", "/fr", "/en", "/es", "/de", "/zh"}:
        response.headers["Cache-Control"] = "public, max-age=300"

    return response
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

def cleanup_files(video_path, audio_path, frame_dir, audio_exists):
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
        if audio_exists and os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)
    except Exception as e:
        print(f"⚠️ Cleanup: {e}", flush=True)

@app.get("/.well-known/assetlinks.json")
async def assetlinks():
    response = FileResponse(
        "frontend/.well-known/assetlinks.json",
        media_type="application/json"
    )
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.get("/manifest.webmanifest")
async def manifest():
    response = FileResponse(
        "frontend/manifest.webmanifest",
        media_type="application/manifest+json"
    )
    response.headers["Cache-Control"] = "no-cache"
    return response
@app.get("/sw.js")
async def service_worker():
    response = FileResponse("frontend/sw.js", media_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response
# ════════════════════════════════════════════════════════════════
# MODÈLES
# ════════════════════════════════════════════════════════════════
class VideoRequest(BaseModel):
    url:          str
    lang:         str = "fr"
    browser_lang: str = "fr"

class ContinueRequest(BaseModel):
    session_id:   str
    ocr_text:     str = ""
    transcript:   str = ""
    browser_lang: str = "fr"


def _extraction_is_useful(ext) -> bool:
    """Gemini a-t-il reconnu quelque chose d'exploitable ?"""
    if not ext: 
        return False
    if ext.get("is_ai_generated"):
        return True
    return bool(ext.get("titres_possibles") or ext.get("acteurs"))















def _has_exact_title(extraction: dict | None) -> bool:
    if not extraction:
        return False

    for t in extraction.get("titres_possibles", []) or []:
        s = str(t or "").strip()
        if s and not s.startswith("?"):
            return True

    return bool(extraction.get("titre_exact"))


def _sanitize_actors_for_search(extraction: dict | None) -> dict:
    """
    Empêche les acteurs halluciné par Gemini/Qwen/OpenRouter de polluer TMDB.
    On garde les acteurs seulement s'ils sont très sûrs.
    """
    if not extraction:
        return extraction or {}

    extraction = dict(extraction)

    actors = extraction.get("acteurs") or []
    certs = extraction.get("acteurs_certitude") or []
    source = str(extraction.get("source", "")).lower()

    if not actors:
        return extraction

    has_exact_title = _has_exact_title(extraction)

    # Sources vidéo LLM : très fortes en description, mais peuvent halluciner les visages.
    video_sources = (
        "qwen" in source
        or "gemini" in source
        or "openrouter" in source
        or "video" in source
    )

    # Si le titre est seulement hypothétique, on durcit beaucoup.
    # Ex: titres=['?The Covenant'] → acteurs à ignorer sauf certitude énorme.
    if video_sources and not has_exact_title:
        min_cert = 92
    elif video_sources:
        min_cert = 88
    else:
        min_cert = 85

    kept_actors = []
    kept_certs = []

    for i, actor in enumerate(actors):
        actor_name = str(actor or "").strip()
        if not actor_name:
            continue

        try:
            cert = int(certs[i]) if i < len(certs) else 0
        except Exception:
            cert = 0

        if cert >= min_cert:
            kept_actors.append(actor_name)
            kept_certs.append(cert)
        else:
            print(
                f"🧹 Acteur ignoré car trop incertain: "
                f"{actor_name} ({cert}<{min_cert}, source={source or 'unknown'})",
                flush=True,
            )

    # Sécurité supplémentaire :
    # si le modèle a proposé un titre avec "?" et moins de 2 acteurs très sûrs,
    # on coupe la recherche acteurs pour éviter les faux candidats.
    titles = extraction.get("titres_possibles") or []
    has_only_uncertain_titles = bool(titles) and all(
        str(t or "").strip().startswith("?") for t in titles
    )

    if has_only_uncertain_titles and len(kept_actors) < 2:
        if kept_actors:
            print(
                "🧹 Acteurs supprimés : titre uniquement hypothétique "
                "et pas assez d'acteurs confirmés.",
                flush=True,
            )
        kept_actors = []
        kept_certs = []

    extraction["acteurs"] = kept_actors
    extraction["acteurs_certitude"] = kept_certs

    return extraction



# ════════════════════════════════════════════════════════════════
# TÂCHE DE FOND : download + analyse complète
# ════════════════════════════════════════════════════════════════
async def _process_local_file(
    session: dict,
    video_path: str,
    audio_path: str,
    frame_dir: str,
    url_label: str,
    lang: str,
    browser_lang: str,
) -> bool:
    """
    Fichier vidéo LOCAL (téléchargé OU uploadé).

    Mode économique :
      1) Conversion codec + validation durée
      2) Gemini vidéo fichier
         → si extraction utile : STOP
      3) Qwen VL vidéo
         → appelé seulement si Gemini échoue ou ne trouve rien
         → si extraction utile : STOP
      4) OpenRouter vidéo direct
         → appelé seulement si Gemini + Qwen échouent
         → si extraction utile : STOP
      5) Audio + frames + transcription
      6) process_analysis via frames
      7) Fallback client si aucune frame mais audio disponible

    Retourne True si un fallback client est en attente
    et qu'il ne faut pas nettoyer les fichiers immédiatement.
    """
    audio_exists = False
    session["status"] = "processing"

    async def _finish_with_extraction(ext: dict, label: str) -> bool:
        print(f"✅ {label} → process_analysis sans frames", flush=True)

        result = await process_analysis(
            frames=[],
            ocr_text="",
            transcript=ext.get("_transcript_raw", ""),
            url=url_label,
            lang=lang,
            browser_lang=browser_lang,
            prefetched_extraction=ext,
        )

        session["status"] = "done"
        session["result"] = result
        return False

    # ── 1. Conversion codec si nécessaire ───────────────────────
    if video_path.endswith(".mp4"):
        try:
            probe = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            codec = probe.stdout.strip()

            if codec and codec not in ("h264", "hevc", "h265", "avc"):
                converted = video_path.replace(".mp4", "_conv.mp4")

                await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg",
                        "-i", video_path,
                        "-c:v", "libx264",
                        "-crf", "23",
                        "-preset", "fast",
                        "-c:a", "aac",
                        "-y", converted,
                    ],
                    capture_output=True,
                    timeout=60,
                )

                if os.path.exists(converted) and os.path.getsize(converted) > 1000:
                    os.remove(video_path)
                    os.rename(converted, video_path)

        except Exception as e:
            print(f"⚠️ Probe/convert: {e}", flush=True)

    # ── 1b. Validation durée ────────────────────────────────────
    duration = 0.0

    try:
        dur = await asyncio.to_thread(
            subprocess.run,
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        duration = float(dur.stdout.strip() or 0)

        if 0 < duration < 3:
            session["status"] = "error"
            session["result"] = {
                "status": "error",
                "code": "video_too_short",
                "message": (
                    f"Vidéo trop courte ({duration:.1f}s). "
                    "Essayez au moins 3 secondes."
                ),
            }
            return False

    except Exception:
        pass

    # ── 2. Gemini vidéo fichier — modèle principal ──────────────
    gemini_path = video_path

    if duration > GEMINI_MAX_SECONDS:
        try:
            base, _ext = os.path.splitext(video_path)
            trimmed = f"{base}_g{GEMINI_MAX_SECONDS}.mp4"

            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-i", video_path,
                    "-t", str(GEMINI_MAX_SECONDS),
                    "-c", "copy",
                    "-y", trimmed,
                ],
                capture_output=True,
                timeout=30,
            )

            if os.path.exists(trimmed) and os.path.getsize(trimmed) > 1000:
                gemini_path = trimmed
                print(
                    f"✂️ Tronquée à {GEMINI_MAX_SECONDS}s pour Gemini "
                    f"(vidéo de {duration:.0f}s)",
                    flush=True,
                )

        except Exception as e:
            print(f"⚠️ Troncature Gemini KO: {e} → vidéo entière", flush=True)

    print("🎬 Gemini sur la vidéo (fichier)...", flush=True)

    try:
        from core.extraction import _extract_gemini_video_file

        file_ext = await _extract_gemini_video_file(gemini_path)

        if _extraction_is_useful(file_ext):
            return await _finish_with_extraction(
                file_ext,
                "Gemini fichier concluant",
            )

        print("⚠️ Gemini fichier non concluant → fallback Qwen VL", flush=True)

    except Exception as e:
        print(f"⚠️ Gemini fichier KO: {e} → fallback Qwen VL", flush=True)

    finally:
        if gemini_path != video_path and os.path.exists(gemini_path):
            try:
                os.remove(gemini_path)
            except Exception:
                pass

    # ── 3. Qwen VL vidéo — fallback seulement si Gemini échoue ──
    QWEN_MAX_SECONDS = 90
    qwen_path = video_path

    if duration > QWEN_MAX_SECONDS:
        try:
            base, _ext = os.path.splitext(video_path)
            qwen_trimmed = f"{base}_q{QWEN_MAX_SECONDS}.mp4"

            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-i", video_path,
                    "-t", str(QWEN_MAX_SECONDS),
                    "-c", "copy",
                    "-y", qwen_trimmed,
                ],
                capture_output=True,
                timeout=30,
            )

            if os.path.exists(qwen_trimmed) and os.path.getsize(qwen_trimmed) > 1000:
                qwen_path = qwen_trimmed
                print(f"✂️ Tronquée à {QWEN_MAX_SECONDS}s pour Qwen VL", flush=True)

        except Exception as e:
            print(f"⚠️ Troncature Qwen KO: {e} → vidéo entière", flush=True)

    try:
        from core.extraction import _extract_qwen_vl

        qwen_ext = await _extract_qwen_vl(qwen_path)

        if _extraction_is_useful(qwen_ext):
            return await _finish_with_extraction(
                qwen_ext,
                "Qwen VL concluant",
            )

        print("⚠️ Qwen VL non concluant → fallback OpenRouter vidéo", flush=True)

    except Exception as e:
        print(f"⚠️ Qwen VL KO: {e} → fallback OpenRouter vidéo", flush=True)

    finally:
        if qwen_path != video_path and os.path.exists(qwen_path):
            try:
                os.remove(qwen_path)
            except Exception:
                pass

    # ── 4. OpenRouter vidéo direct — dernier fallback vidéo ─────
        # ── 4. OpenRouter vidéo direct — désactivé par défaut ───────
    # Important :
    # OpenRouter vidéo demande une balance payante dans ton cas.
    # Sur Render 512 MB, on évite aussi la compression ffmpeg inutile.
    if os.environ.get("OPENROUTER_VIDEO_ENABLED", "false").lower() == "true":
        openrouter_path = video_path
        openrouter_generated_path = None

        try:
            OPENROUTER_MAX_SECONDS = int(
                os.environ.get("OPENROUTER_MAX_VIDEO_SECONDS", "45")
            )
            OPENROUTER_VIDEO_HEIGHT = int(
                os.environ.get("OPENROUTER_VIDEO_HEIGHT", "480")
            )

            base, _ext = os.path.splitext(video_path)
            openrouter_generated_path = f"{base}_or{OPENROUTER_MAX_SECONDS}.mp4"

            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-i", video_path,
                    "-t", str(OPENROUTER_MAX_SECONDS),
                    "-map", "0:v:0",
                    "-map", "0:a?",
                    "-vf", f"scale=-2:{OPENROUTER_VIDEO_HEIGHT}",
                    "-r", "12",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "30",
                    "-c:a", "aac",
                    "-b:a", "64k",
                    "-ac", "1",
                    "-ar", "16000",
                    "-movflags", "+faststart",
                    "-y", openrouter_generated_path,
                ],
                capture_output=True,
                timeout=75,
            )

            if (
                os.path.exists(openrouter_generated_path)
                and os.path.getsize(openrouter_generated_path) > 1000
            ):
                openrouter_path = openrouter_generated_path

                print(
                    f"🎬 Vidéo optimisée OpenRouter "
                    f"({os.path.getsize(openrouter_path) / 1024 / 1024:.1f} MB)",
                    flush=True,
                )

            else:
                print("⚠️ Compression OpenRouter KO → vidéo originale", flush=True)
                openrouter_path = video_path

            try:
                from core.extraction import _extract_openrouter_video

                openrouter_ext = await _extract_openrouter_video(openrouter_path)

                if _extraction_is_useful(openrouter_ext):
                    return await _finish_with_extraction(
                        openrouter_ext,
                        "OpenRouter vidéo concluant",
                    )

                print(
                    "⚠️ OpenRouter vidéo non concluant → frames + transcription",
                    flush=True,
                )

            except Exception as e:
                print(
                    f"⚠️ OpenRouter vidéo exception: {str(e)[:120]} "
                    "→ frames + transcription",
                    flush=True,
                )

        except Exception as e:
            print(
                f"⚠️ Préparation OpenRouter vidéo KO: {str(e)[:120]} "
                "→ frames + transcription",
                flush=True,
            )

        finally:
            if (
                openrouter_generated_path
                and openrouter_generated_path != video_path
                and os.path.exists(openrouter_generated_path)
            ):
                try:
                    os.remove(openrouter_generated_path)
                except Exception:
                    pass

    else:
        print("ℹ️ OpenRouter vidéo désactivé → frames + transcription", flush=True)

    # ── 5. Audio ────────────────────────────────────────────────
    try:
        await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg",
                "-i", video_path,
                "-t", str(MAX_VIDEO_SECONDS),
                "-vn",
                "-acodec", "libmp3lame",
                "-ar", "16000",
                "-ac", "1",
                "-b:a", "64k",
                "-y", audio_path,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        audio_exists = (
            os.path.exists(audio_path)
            and os.path.getsize(audio_path) > 100
        )

    except Exception:
        try:
            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-i", video_path,
                    "-t", str(MAX_VIDEO_SECONDS),
                    "-vn",
                    "-ar", "16000",
                    "-ac", "1",
                    "-f", "mp3",
                    "-y", audio_path,
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )

            audio_exists = (
                os.path.exists(audio_path)
                and os.path.getsize(audio_path) > 100
            )

        except Exception as e2:
            print(f"⚠️ Audio KO: {str(e2)[:80]}", flush=True)

    # ── 6. Frames ───────────────────────────────────────────────
    # extract_keyframes() enchaîne plusieurs appels ffmpeg/ffprobe
    # bloquants (subprocess.run avec timeouts en cascade, jusqu'à ~90s
    # cumulés dans le pire cas). Appelé directement, ça gèle toute la
    # boucle asyncio — avec WEB_CONCURRENCY=1, ça bloque littéralement
    # tout le serveur pour tout le monde, et au-delà du timeout gunicorn
    # ça se termine en WORKER TIMEOUT/SIGABRT (perte de la requête en
    # cours ET de toutes les requêtes en attente sur ce worker).
    try:
        frames = await asyncio.to_thread(extract_keyframes, video_path, frame_dir, max_frames=6) or []
    except Exception as e:
        print(f"⚠️ Keyframes: {e}", flush=True)
        frames = []

    frames = [
        f for f in frames
        if os.path.exists(f) and os.path.getsize(f) > 0
    ]

    print(f"✅ Frames valides: {len(frames)}", flush=True)

    if not frames and not audio_exists:
        session["status"] = "error"
        session["result"] = {
            "status": "error",
            "code": "no_frames",
            "message": "Impossible d'extraire des images ou de l'audio de cette vidéo.",
        }
        return False

    # ── 7. Transcription ────────────────────────────────────────
    transcript = ""

    if audio_exists:
        try:
            transcript = await asyncio.to_thread(transcribe, audio_path, enabled=True) or ""
        except Exception as e:
            print(f"⚠️ Transcription KO: {e}", flush=True)

    # ── 8. Analyse via frames ───────────────────────────────────
    if frames:
        result = await process_analysis(
            frames,
            "",
            transcript,
            url_label,
            lang,
            browser_lang,
        )

        session["status"] = "done"
        session["result"] = result
        return False

    # ── 9. Fallback client si aucune frame mais audio disponible ─
    audio_b64 = ""

    if audio_exists:
        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
        except Exception:
            pass

    fallback_sid = str(uuid.uuid4())[:12]

    sessions[fallback_sid] = {
        "url": url_label,
        "lang": lang,
        "browser_lang": browser_lang,
        "video_path": video_path,
        "audio_path": audio_path,
        "frame_dir": frame_dir,
        "ocr_text": "",
        "timestamp": time.time(),
    }

    session["status"] = "done"
    session["result"] = {
        "status": "transcription_needed",
        "session_id": fallback_sid,
        "frames_base64": [],
        "audio_base64": audio_b64,
    }

    return True





async def _run_download_and_analyse(session_id, url, platform, lang, browser_lang):
    session = _dl_sessions.get(session_id)
    if not session:
        return

    video_path = session["video_path"]
    audio_path = session["audio_path"]
    frame_dir = session["frame_dir"]

    need_client_fallback = False

    async with _analysis_semaphore:
        try:
            # URL directe Gemini UNIQUEMENT pour YouTube.
            # Toutes les autres plateformes passent par download_video(...)
            # donc : tikwm → yt-dlp selon universal_downloader.py.
            if platform == "youtube":
                session["status"] = "processing"

                try:
                    from core.extraction import _extract_gemini_url_direct

                    extraction = await _extract_gemini_url_direct(url)

                    if _extraction_is_useful(extraction):
                        result = await process_analysis(
                            frames=[],
                            ocr_text="",
                            transcript=extraction.get("_transcript_raw", ""),
                            url=url,
                            lang=lang,
                            browser_lang=browser_lang,
                            prefetched_extraction=extraction,
                        )

                        session["status"] = "done"
                        session["result"] = result
                        return

                    print("⚠️ URL YouTube directe non concluante → download", flush=True)

                except Exception as e:
                    print(
                        f"⚠️ URL YouTube directe exception: {str(e)[:120]} → download",
                        flush=True,
                    )

            else:
                print(
                    f"ℹ️ [{platform}] → pas de Gemini URL directe, passage au téléchargement",
                    flush=True,
                )

            # Download :
            # YouTube fallback → worker/yt-dlp
            # Autres plateformes → tikwm puis yt-dlp
            session["status"] = "downloading"
            print(f"📥 DOWNLOAD [{platform}] session={session_id}", flush=True)

            dl = await download_video(url, video_path, platform)

            if not dl.get("ok"):
                session["status"] = "error"
                session["result"] = {
                    "status": "error",
                    "code": dl.get("code", "download_failed"),
                    "message": dl.get(
                        "message",
                        "Impossible de télécharger cette vidéo.",
                    ),
                }
                return

            if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
                session["status"] = "error"
                session["result"] = {
                    "status": "error",
                    "code": "download_empty",
                    "message": "Le fichier vidéo est vide ou corrompu.",
                }
                return

            print(
                f"✅ Vidéo téléchargée "
                f"({os.path.getsize(video_path) / 1024 / 1024:.1f} MB)",
                flush=True,
            )

            need_client_fallback = await _process_local_file(
                session,
                video_path,
                audio_path,
                frame_dir,
                url,
                lang,
                browser_lang,
            )

        except Exception:
            print(
                f"❌ _run_download_and_analyse: {traceback.format_exc()}",
                flush=True,
            )

            session["status"] = "error"
            session["result"] = {
                "status": "error",
                "code": "unexpected",
                "message": "Une erreur inattendue s'est produite. Réessayez.",
            }

        finally:
            if not need_client_fallback:
                cleanup_files(video_path, audio_path, frame_dir, True)

            session["timestamp"] = time.time()

            lock_key = session.get("_lock_key")
            lock_token = session.get("_lock_token")

            if lock_key and lock_token:
                release_lock(lock_key, lock_token)


@app.post("/analyser") 
async def analyser(req: VideoRequest, request: Request):
    ip = _get_client_ip(request)
    rate_err = _check_rate_limit(ip)
    if rate_err:
        print(f"🚫 Rate limit [{ip}]", flush=True)
        return rate_err

    url      = await _resolve_short_url(req.url.strip())
    url      = normalize_url(url)
    platform = detect_platform(url)
    print(f"\n📥 ANALYSE [{platform}] lang={req.lang} browser={req.browser_lang}: {url[:80]}", flush=True)

    if not SUPPORTED_PLATFORMS.search(url):
        return {"status": "error", "code": "unsupported_platform",
                "message": "Cette plateforme n'est pas supportée. "
                           "Essayez TikTok, Instagram, YouTube, Twitter/X, Facebook ou Dailymotion."}

    cached = get_cache(url)
    if cached:
        return {"status": "cached", **cached}

    # ── Verrou anti-doublons : empêche plusieurs requêtes concurrentes ──
    # sur la même URL non-cachée de relancer chacune le pipeline complet
    # (download + Gemini + cascade). La première requête pose le verrou
    # et traite normalement ; les suivantes attendent brièvement puis
    # retentent le cache, sans jamais lancer leur propre download/Gemini.
    from storage.cache_engine.hash_utils import key_url
    lock_key = key_url(url)
    lock_token = acquire_lock(lock_key, ttl=900)

    if lock_token is None:
        # Une analyse de cette URL est déjà en cours.
        # Surtout NE PAS relancer download + ffmpeg + LLM en parallèle.
        max_wait_seconds = 60
        poll_interval = 2
        attempts = int(max_wait_seconds / poll_interval)

        for _ in range(attempts):
            await asyncio.sleep(poll_interval)

            cached = get_cache(url)
            if cached:
                print(f"✅ Cache hit après attente verrou: {url[:60]}", flush=True)
                return {"status": "cached", **cached}

        print(
            f"⏳ Analyse déjà en cours pour cette URL, refus de duplication: {url[:60]}",
            flush=True,
        )

        return {
            "status": "error",
            "code": "analysis_already_running",
            "message": (
                "Cette vidéo est déjà en cours d'analyse. "
                "Attendez quelques secondes puis réessayez."
            ),
        }

    if _analysis_semaphore.locked():
        if lock_token:
            release_lock(lock_key, lock_token)
        return {"status": "error", "code": "server_busy",
                "message": "Le serveur analyse déjà plusieurs vidéos. Réessayez dans 30 secondes."}

    uid        = str(uuid.uuid4())[:8]
    session_id = str(uuid.uuid4())[:12]
    os.makedirs("temp", exist_ok=True)

    _dl_sessions[session_id] = {
        "uid":          uid,
        "url":          url,
        "lang":         req.lang,
        "browser_lang": req.browser_lang,
        "platform":     platform,
        "video_path":   f"temp/{uid}.mp4",
        "audio_path":   f"temp/{uid}.mp3",
        "frame_dir":    f"temp/{uid}",
        "status":       "queued",
        "result":       None,
        "timestamp":    time.time(),
        "_lock_key":    lock_key,
        "_lock_token":  lock_token,
    }

    asyncio.create_task(
        _run_download_and_analyse(
            session_id, url, platform, req.lang, req.browser_lang
        )
    )

    return {"status": "processing", "session_id": session_id}

async def _run_uploaded_analyse(session_id, lang, browser_lang):
    session = _dl_sessions.get(session_id)
    if not session:
        return
    vp, ap, fd = session["video_path"], session["audio_path"], session["frame_dir"]
    need_client_fallback = False
    async with _analysis_semaphore:      # ← ajouté
        try:
            need_client_fallback = await _process_local_file(
                session, vp, ap, fd, session["url"], lang, browser_lang)
        except Exception:
            print(f"❌ _run_uploaded_analyse: {traceback.format_exc()}", flush=True)
            session["status"] = "error"
            session["result"] = {"status": "error", "code": "unexpected",
                                 "message": "Une erreur inattendue s'est produite. Réessayez."}
        finally:
            if not need_client_fallback:
                cleanup_files(vp, ap, fd, True)
            session["timestamp"] = time.time()
@app.post("/analyser-upload")
async def analyser_upload(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("fr"),
    browser_lang: str = Form("fr"),
):
    ip = _get_client_ip(request)
    rate_err = _check_rate_limit(ip)
    if rate_err:
        return rate_err
    if _analysis_semaphore.locked():
        return {"status": "error", "code": "server_busy",
                "message": "Le serveur analyse déjà plusieurs vidéos. Réessayez dans 30 secondes."}
    if not (file.content_type or "").startswith("video/"):
        return {"status": "error", "code": "unsupported",
                "message": "Le fichier doit être une vidéo (mp4, mov, webm…)."}

    uid = str(uuid.uuid4())[:8]; session_id = str(uuid.uuid4())[:12]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    size = 0
    try:
        with open(video_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    if os.path.exists(video_path):
                        os.remove(video_path)
                    return {"status": "error", "code": "file_too_large",
                            "message": f"Fichier trop volumineux (max {MAX_FILE_SIZE_MB} Mo)."}
                out.write(chunk)
    except Exception as e:
        print(f"❌ upload write: {e}", flush=True)
        return {"status": "error", "code": "unexpected", "message": "Échec de l'upload."}

    if size < 1000:
        if os.path.exists(video_path):
            os.remove(video_path)
        return {"status": "error", "code": "download_empty", "message": "Fichier vide ou corrompu."}

    print(f"📤 UPLOAD reçu ({size/1024/1024:.1f} MB) session={session_id}", flush=True)
    _dl_sessions[session_id] = {
        "uid": uid, "url": f"upload:{uid}", "lang": lang, "browser_lang": browser_lang,
        "platform": "upload", "video_path": video_path,
        "audio_path": f"temp/{uid}.mp3", "frame_dir": f"temp/{uid}",
        "status": "queued", "result": None, "timestamp": time.time()}
    asyncio.create_task(_run_uploaded_analyse(session_id, lang, browser_lang))
    return {"status": "processing", "session_id": session_id}

# ════════════════════════════════════════════════════════════════
# POLLING
# ════════════════════════════════════════════════════════════════

POLLING_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Robots-Tag": "noindex, nofollow",
}


def _polling_json(payload: dict) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers=POLLING_NO_STORE_HEADERS,
    )


@app.get("/analyser_status/{session_id}")
# Compatibilité temporaire avec l’ancienne URL encore présente dans certains caches
@app.get("/analyseur_status/{session_id}", include_in_schema=False)
async def analyser_status(session_id: str):
    session = _dl_sessions.get(session_id)

    if not session:
        return _polling_json({
            "status": "error",
            "code": "session_expired",
            "message": "Session expirée ou introuvable. Relancez l'analyse.",
        })

    current_status = session.get("status", "queued")

    if current_status in ("queued", "downloading", "processing"):
        # Ne rafraîchit le timestamp que pendant le traitement actif :
        # une fois "done"/"error", on fige le timestamp à l'instant de la
        # complétion pour laisser cleanup_sessions() l'expirer proprement
        # après DL_SESSION_TIMEOUT, sans dépendre du polling client.
        session["timestamp"] = time.time()

        retry_after_ms = {
            "queued": 4000,
            "downloading": 5000,
            "processing": 8000,
        }.get(current_status, 8000)

        return _polling_json({
            "status": "processing",
            "step": current_status,
            "retry_after_ms": retry_after_ms,
        })

    result = session.get("result") or {
        "status": "error",
        "code": "unexpected",
        "message": "Résultat manquant.",
    }

    # Important : on NE supprime PLUS la session ici. Si la réponse HTTP
    # est perdue en route (coupure réseau, worker redémarré par Render en
    # plein envoi — cf. logs SIGTERM), le prochain poll du même
    # session_id doit pouvoir récupérer le même résultat au lieu de
    # tomber sur "session_expired" alors que l'analyse a bien abouti.
    # cleanup_sessions() se charge de la purge après DL_SESSION_TIMEOUT.
    return _polling_json(result)

# ════════════════════════════════════════════════════════════════
# FALLBACK TRANSCRIPTION CÔTÉ CLIENT
# ════════════════════════════════════════════════════════════════
@app.post("/analyser_continue")
async def analyser_continue(req: ContinueRequest):
    session = sessions.get(req.session_id)
    if not session:
        return {"status": "error", "code": "session_expired",
                "message": "Session expirée. Relancez l'analyse."}
    try:
        ocr_text     = req.ocr_text   or ""
        transcript   = req.transcript or ""
        browser_lang = req.browser_lang or session.get("browser_lang", "fr")
        frame_dir    = session["frame_dir"]
        frames_paths = []
        if os.path.exists(frame_dir):
            frames_paths = sorted([
                os.path.join(frame_dir, f)
                for f in os.listdir(frame_dir)
                if f.endswith((".jpg", ".png"))
                and os.path.getsize(os.path.join(frame_dir, f)) > 0
            ])
        if not frames_paths and not ocr_text and not transcript:
            return {"status": "error", "code": "no_data",
                    "message": "Aucune donnée disponible pour l'analyse. Relancez."}
        return await process_analysis(
            frames_paths, ocr_text, transcript,
            session["url"], session["lang"], browser_lang,
        )
    except Exception as e:
        print(f"❌ analyser_continue: {e}", flush=True)
        return {"status": "error", "code": "unexpected",
                "message": "Erreur lors de l'analyse. Réessayez."}
    finally:
        s = sessions.pop(req.session_id, None)
        if s:
            for key in ("video_path", "audio_path", "frame_dir"):
                p = s.get(key)
                if p and os.path.exists(p):
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)









# ════════════════════════════════════════════════════════════════
# PURGE CACHE
# ════════════════════════════════════════════════════════════════
@app.delete("/cache-purge-url")
async def cache_purge_url(url: str):
    try:
        from storage.cache import delete_cache
        normalized = normalize_url(url.strip())
        deleted    = delete_cache(normalized)
        return {"status": "ok", "deleted": deleted, "url": normalized}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/cache-purge-code/{code}")
async def cache_purge_code(code: str):
    try:
        from storage.cache import purge_by_code
        count = purge_by_code(code)
        return {"status": "ok", "purged": count, "code": code}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ════════════════════════════════════════════════════════════════
# PROCESS ANALYSIS
# ════════════════════════════════════════════════════════════════


async def _finalize_with_known_result(
    url: str,
    lang: str,
    browser_lang: str,
    transcript: str,
    ocr_text: str,
    fake_score: int,
    result: dict,
    candidates: list,
    alternatives: list | None = None,
) -> dict:
    """
    Finalise une analyse à partir d'un résultat déjà connu (match embeddings,
    ou tout autre cas où le rerank a déjà été fait en amont). Reprend la
    logique "Détails TMDB" de process_analysis() sans dupliquer le code.

    Paramètres :
      result       : dict avec au moins {id, media_type, meilleur_titre, score}
      candidates   : liste de candidats (peut être minimaliste, juste pour
                     permettre au code de retrouver le media_type si besoin)
      alternatives : classement composite des candidats suivants (rank_opinions),
                     exposés au frontend si la confiance du résultat principal
                     est sous MULTI_CANDIDATE_THRESHOLD
    """
    confidence = result.get("score", 0)
    alternatives = alternatives or []

    if confidence >= SHOULD_SHOW_ALTERNATIVES_BELOW and result.get("id"):
        film_hit = get_cache_by_film(result["id"], lang)
        if film_hit:
            set_cache(url, film_hit, transcript=transcript or "", ocr_text=ocr_text or "")
            return {"status": "cached", **film_hit}

    if confidence <= 40:
        titre    = result.get("meilleur_titre", "")
        low_conf = {
            "status":         "not_found",
            "message":        f"Film non identifié avec certitude ({confidence}%). Essayez de rechercher manuellement.",
            "titre_gemini":   titre,
            "search_youtube": f"https://www.youtube.com/results?search_query={titre}+film+trailer",
        }
        set_cache(url, low_conf, transcript=transcript or "", ocr_text=ocr_text or "")
        return low_conf

    movie_id       = result["id"]
    effective_type = result.get("media_type", "movie")

    if not effective_type or effective_type == "mixed":
        matched = next(
            (c for c in candidates if c.get("id") == movie_id), None
        )
        effective_type = (matched.get("media_type", "movie") if matched else "movie")

    print(f"📋 Détails TMDB id={movie_id} type={effective_type}", flush=True)

    details_lang = browser_lang or lang

    try:
        details = (
            await get_tv_details(movie_id, details_lang)
            if effective_type == "tv"
            else await get_movie_details(movie_id, details_lang)
        )
    except Exception:
        try:
            if effective_type == "tv":
                details        = await get_movie_details(movie_id, details_lang)
                effective_type = "movie"
            else:
                details        = await get_tv_details(movie_id, details_lang)
                effective_type = "tv"
        except Exception as e2:
            print(f"❌ TMDB KO id={movie_id}: {e2}", flush=True)
            return {"status": "error", "code": "tmdb_error",
                    "message": "Impossible de récupérer les détails du film."}

    region = _get_region_from_lang(browser_lang)
    providers = (
        details.get("watch/providers", {})
               .get("results", {})
               .get(region, {})
               .get("flatrate", [])
    )
    is_series = effective_type == "tv" or bool(details.get("first_air_date"))

    final = {
        "status":          "success",
        "media_type":      effective_type,
        "is_series":       is_series,
        "title":           (result.get("meilleur_titre")
                            or details.get("title")
                            or details.get("name")
                            or "Inconnu"),
        "confidence":      max(0, confidence),
        "_lowConfWarning":  confidence < SHOULD_SHOW_ALTERNATIVES_BELOW,
        "synopsis":        details.get("overview", ""),
        "image":           (f"https://image.tmdb.org/t/p/w500{details['poster_path']}"
                            if details.get("poster_path") else ""),
        "streaming":       [p.get("provider_name") for p in providers],
        "streaming_logos": [
            {"name": p.get("provider_name"), "logo_path": p.get("logo_path")}
            for p in providers
        ],
        "similar": [
            {
                "title":       s.get("title", s.get("name", "?")),
                "id":          s.get("id"),
                "poster_path": s.get("poster_path"),
            }
            for s in details.get("similar", {}).get("results", [])[:6]
        ],
        "cast": [
            {
                "name":         c.get("name"),
                "character":    c.get("character"),
                "profile_path": c.get("profile_path"),
            }
            for c in details.get("credits", {}).get("cast", [])[:8]
        ],
        "trailer":      "",
        "genres":       [g["name"] for g in details.get("genres", [])],
        "year":         (details.get("release_date")
                         or details.get("first_air_date") or "").split("-")[0],
        "runtime":      (details.get("runtime")
                         or (details.get("episode_run_time") or [None])[0]),
        "vote_average": details.get("vote_average"),
        "vote_count":   details.get("vote_count"),
        "tmdb_id":      movie_id,
        "lang":         lang,
        "is_fake":      fake_score > 70,
        "seasons":      details.get("seasons") if is_series else None,
    }

    # ── Multi-candidats : propose des alternatives si confiance faible ──
    # ── Multi-candidats façon Shazam ─────────────────────────────
# On propose plusieurs films si la confiance est moyenne/faible.
# Même si le score dépasse légèrement le seuil, on garde des alternatives
# quand le résultat n'est pas ultra sûr.
    show_multi_candidates = _should_show_shazam_choices(
    result,
    alternatives,
    hard_threshold=SHOULD_SHOW_ALTERNATIVES_BELOW,
    close_gap=ALTERNATIVES_CLOSE_GAP,
)

    if show_multi_candidates and alternatives:
        alt_details = []
        for alt in alternatives[:4]:
            try:
                d = (
                    await get_tv_details(alt["id"], details_lang)
                    if alt.get("media_type") == "tv"
                    else await get_movie_details(alt["id"], details_lang)
                    )
                alt_details.append({
                    "id":          alt["id"],
                    "title":       alt.get("meilleur_titre") or d.get("title") or d.get("name"),
                    "media_type":  alt.get("media_type", "movie"),
                    "poster_path": d.get("poster_path"),
                    "year":        (d.get("release_date") or d.get("first_air_date") or "")[:4],
                    "confidence":  alt.get("score", 0),
                })
            except Exception:
                continue

        if alt_details:
            final["alternatives"] = alt_details
            final["needs_confirmation"] = True
            final["message"] = (
            "Nous pensons avoir trouvé le film, mais voici d'autres possibilités proches."
            )

# Cache toujours le résultat final fiable, avec ou sans alternatives
    if confidence >= 50:
        set_cache(url, final, transcript=transcript or "", ocr_text=ocr_text or "")

    return final






def _make_candidate_alternatives(
    candidates: list,
    best_result: dict,
    max_items: int = 4,
) -> list:
    """
    Fabrique des alternatives façon Shazam à partir des candidats TMDB.
    On exclut le résultat principal et on garde les candidats les plus plausibles.
    """
    if not candidates or not best_result:
        return []

    best_id = best_result.get("id")
    alternatives = []

    for c in candidates:
        if c.get("id") == best_id:
            continue

        title = c.get("title") or c.get("name") or ""
        if not title:
            continue

        media_type = c.get("media_type")
        if not media_type:
            media_type = "tv" if c.get("first_air_date") else "movie"

        year = (c.get("release_date") or c.get("first_air_date") or "")[:4]

        # Score indicatif : ce n'est pas une certitude LLM,
        # juste une plausibilité pour affichage.
        alt_score = max(
            35,
            min(
                82,
                int((c.get("vote_average") or 5) * 8)
            )
        )

        alternatives.append({
            "id": c.get("id"),
            "meilleur_titre": title,
            "media_type": media_type,
            "score": alt_score,
            "year": year,
        })

        if len(alternatives) >= max_items:
            break

    return alternatives


async def process_analysis(
    frames,
    ocr_text,
    transcript,
    url,
    lang,
    browser_lang: str | None = None,
    prefetched_extraction: dict | None = None,
):
    browser_lang = browser_lang or lang

    # ── 1. Cache niveau contenu ──────────────────────────────────
    if transcript or ocr_text:
        content_hit = get_cache_by_content(transcript, ocr_text, lang)
        if content_hit:
                set_cache(url, content_hit, transcript=transcript, ocr_text=ocr_text)
                return {"status": "cached", **content_hit}

    # ── 1b. Check embeddings (avant les LLM) ──────────────────────
    if prefetched_extraction is None and (transcript or ocr_text or frames):
        embedding_match = await check_known_film(
            transcript=transcript or "",
            ocr_text=ocr_text or "",
            frame_paths=frames or [],
        )
        if embedding_match:
            tmdb_id_match    = embedding_match["tmdb_id"]
            media_type_match = embedding_match.get("media_type", "movie")
            lang_match       = embedding_match.get("lang", lang)

            film_hit = get_cache_by_film(tmdb_id_match, lang_match)
            if film_hit:
                print(
                    f" Match embeddings → cache film direct (tmdb_id={tmdb_id_match}, "
                    f"score={embedding_match['score']:.3f})",
                    flush=True,
                )
                set_cache(url, film_hit, transcript=transcript or "", ocr_text=ocr_text or "")
                return {"status": "cached", **film_hit}

            print(
                f"⚡ Match embeddings sans cache fiche → identification directe "
                f"(tmdb_id={tmdb_id_match}, score={embedding_match['score']:.3f})",
                flush=True,
            )
            fake_score_preliminary = detect_fake((ocr_text or "") + " " + (transcript or ""))
            result = {
                "id":             tmdb_id_match,
                "media_type":     media_type_match,
                "meilleur_titre": "",
                "score":          75,
                "raison":         "match embeddings (similarité élevée)",
            }
            candidates = [{
                "id": tmdb_id_match, "media_type": media_type_match,
                "title": "", "popularity": 0,
            }]
            return await _finalize_with_known_result(
                url, lang, browser_lang, transcript, ocr_text,
                fake_score=fake_score_preliminary,
                result=result, candidates=candidates,
            )

    # ── 2. Extraction multimodale ────────────────────────────────
    if prefetched_extraction is not None:
        extraction = prefetched_extraction
        print("✅ Extraction prefetchée utilisée", flush=True)
        detected_script = extraction.get("detected_script", "latin")
    else:
        combined_text   = (transcript or "") + " " + (ocr_text or "")
        detected_script = "latin"
        if re.search(r"[؀-ۿݐ-ݿ]", combined_text):
            detected_script = "arabic"
        elif re.search(r"[一-鿿㐀-䶿]", combined_text):
            detected_script = "chinese"
        elif re.search(r"[가-힯ᄀ-ᇿ]", combined_text):
            detected_script = "korean"
        elif re.search(r"[぀-ゟ゠-ヿ]", combined_text):
            detected_script = "japanese"
        elif re.search(r"[Ѐ-ӿ]", combined_text):
            detected_script = "cyrillic"
        if detected_script != "latin":
            print(f"🌐 Script détecté: {detected_script}", flush=True)

        extraction = await multimodal_extract(frames, ocr_text, transcript) or {}
        if detected_script != "latin":
            extraction["detected_script"] = detected_script
        extraction["_transcript_raw"] = transcript or ""

# ── 2b. Correction humaine déjà connue pour ce même acteur/titre ──
    known_correction = get_correction_for_extraction(extraction)
    if known_correction:
        print(f"✅ Correction humaine appliquée directement: {known_correction}", flush=True)
        return await _finalize_with_known_result(
            url, lang, browser_lang, transcript, ocr_text,
            fake_score=detect_fake((ocr_text or "") + " " + (transcript or "")),
            result={
                "id":             known_correction["tmdb_id"],
                "media_type":     known_correction["media_type"],
                "meilleur_titre": "",
                "score":          known_correction.get("confidence", 90),
            },
            candidates=[{
                "id": known_correction["tmdb_id"],
                "media_type": known_correction["media_type"],
                "title": "", "popularity": 0,
            }],
        )
    extraction = _sanitize_actors_for_search(extraction)
    
    # ── 2c. Web clue enrichment léger AVANT TMDB ─────────────────
    # Objectif : enrichir extraction_json avec quelques titres/années web,
    # puis laisser run_cascade_search interroger TMDB proprement.
    try:
        web_light_extraction = dict(extraction)

        # Sécurité : le web light ne doit pas amplifier des acteurs halluciné.
        # On garde les acteurs seulement si un titre exact est déjà présent.
        if not _has_exact_title(web_light_extraction):
            web_light_extraction["acteurs"] = []
            web_light_extraction["acteurs_certitude"] = []

        extraction = await light_web_enrich_extraction(
            web_light_extraction,
            ocr_text=ocr_text or "",
            transcript=transcript or "",
            browser_lang=browser_lang,
        )

    except Exception as e:
        print(f"⚠️ Web light enrichment KO: {str(e)[:120]}", flush=True)
    
    
    # ── 3. Langue de la transcription ────────────────────────────
    transcript_lang = extraction.get("langue_originale") or None
    if not transcript_lang and detected_script != "latin":
        _script_to_lang = {
            "arabic":   "ar",
            "chinese":  "zh",
            "korean":   "ko",
            "japanese": "ja",
            "cyrillic": "ru",
        }
        transcript_lang = _script_to_lang.get(detected_script)

    # ── 3b. Correction transcript_lang si titres en langue non-anglaise ──
    _LANG_MARKERS: dict[str, set[str]] = {
        "fr": {"le", "la", "les", "des", "du", "une", "de", "et", "en",
               "dans", "sur", "avec", "pour", "par", "au", "aux",
               "peuple", "abysses", "nuit", "jour", "maison", "femme",
               "homme", "enfant", "monde", "ville", "guerre", "amour"},
        "es": {"el", "la", "los", "las", "del", "una", "de", "en",
               "con", "por", "para", "que", "es", "un", "al"},
        "de": {"der", "die", "das", "des", "dem", "den", "ein", "eine",
               "und", "von", "mit", "auf", "für", "ist", "im"},
        "it": {"il", "la", "lo", "gli", "le", "dei", "del", "della",
               "una", "di", "in", "con", "per", "che", "si"},
        "pt": {"o", "a", "os", "as", "do", "da", "dos", "das",
               "um", "uma", "de", "em", "com", "por", "para"},
    }

    if (
        transcript_lang in ("en", None)
        and browser_lang in _LANG_MARKERS
    ):
        titres = extraction.get("titres_possibles", [])
        desc   = (extraction.get("description_courte") or "").lower()
        titres_text = " ".join(str(t).lstrip("?") for t in titres).lower()
        all_text    = f"{titres_text} {desc}"
        words       = set(re.findall(r'\b\w+\b', all_text))
        markers     = _LANG_MARKERS[browser_lang]

        matched = words & markers
        if len(matched) >= 2:
            print(
                f"🌍 Titres/desc en '{browser_lang}' détectés "
                f"(marqueurs: {matched}) malgré transcript_lang={transcript_lang!r} "
                f"→ forcer transcript_lang='{browser_lang}'",
                flush=True
            )
            transcript_lang = browser_lang

    print(
        f"🌍 Langues — transcription={transcript_lang}, "
        f"navigateur={browser_lang}, interface={lang}",
        flush=True
    )

    # ── 3c. Détection contenu généré par IA ─────────────────────
    if extraction.get("is_ai_generated"):
        print("🤖 Contenu généré par IA détecté → retour immédiat", flush=True)
        ai_result = {
            "status":          "not_found",
            "code":            "ai_generated",
            "message":         (
                "Cette vidéo semble générée par intelligence artificielle "
                "(Sora, Runway, Midjourney, Pika...). "
                "Aucun film réel correspondant n'existe."
            ),
            "is_ai_generated": True,
            "search_google":   f"https://www.google.com/search?q=AI+generated+video+{url[:50]}",
        }
        set_cache(url, ai_result, transcript=transcript or "", ocr_text=ocr_text or "")
        return ai_result

    # ── 4. Cache niveau titre ────────────────────────────────────
    for titre_candidat in extraction.get("titres_possibles", []):
        if str(titre_candidat).startswith("?"):
            continue
        title_hit = get_cache_by_title(titre_candidat, lang)
        if title_hit:
            set_cache(url, title_hit, transcript=transcript, ocr_text=ocr_text)
            return {"status": "cached", **title_hit}

    fake_score = detect_fake((ocr_text or "") + " " + (transcript or ""))
    candidates = []
    result     = None
    opinions   = []   # ← accumule les avis de chaque canal indépendant
    candidate_alternatives = []

    # ── 5 + 5b. Recherche acteurs ET ancrage par réplique exacte ──
    # Les deux canaux sont indépendants l'un de l'autre (aucun ne dépend
    # du résultat de l'autre pour se déclencher) → on lance la recherche
    # de réplique en tâche de fond dès le début, pendant que la recherche
    # acteurs (TMDB + rerank LLM) se déroule normalement.
    actor_candidates = []

    quote_corrob_task = asyncio.create_task(
        find_quote_corroboration(transcript or "", browser_lang=browser_lang)
    )

    if extraction.get("acteurs"):
        actor_candidates = await build_candidates_from_actors(
            extraction,
            lang=transcript_lang or browser_lang or lang,
        )
    else:
        print("🧹 Recherche acteurs ignorée : aucun acteur fiable après filtrage", flush=True)

    actor_rerank_task = (
        asyncio.create_task(rerank(extraction, actor_candidates))
        if actor_candidates else None
    )

    if actor_rerank_task:
        print(f"🎭 Recherche via acteurs: {len(actor_candidates)} candidats", flush=True)
        actor_result = await actor_rerank_task
        opinions.append(make_opinion(actor_result, "actors"))
        if actor_result and actor_result.get("score", 0) >= 50:
            matched = next(
                (c for c in actor_candidates if c.get("id") == actor_result.get("id")),
                None
            )
            if matched:
                actor_result["media_type"] = matched.get("media_type", "movie")
            result     = actor_result
            candidates = actor_candidates
            print(
                f"✅ Acteur-match retenu "
                f"(score={result['score']}, type={result.get('media_type')})",
                flush=True
            )

    # ── 5b. Ancrage par réplique exacte — récupération du résultat déjà en cours ──
    quote_corrob = await quote_corrob_task
    quote_candidate_ids = {c["id"] for c in quote_corrob["candidates"]}

    if quote_corrob["candidates"]:
        candidates_before = candidates or []
        merged = quote_corrob["candidates"] + [
            c for c in candidates_before
            if c.get("id") not in quote_candidate_ids
        ]
        quote_result = await rerank(extraction, merged)
        opinions.append(make_opinion(quote_result, "quote"))
        if quote_result and quote_result.get("score", 0) >= 50:
            result     = quote_result
            candidates = merged
            print(f"✅ Quote-match retenu (score={result['score']})", flush=True)

    if result:
        result = apply_quote_corroboration(result, quote_candidate_ids)

    # ── 6. Fallback : cascade TMDB multi-langue ──────────────────
    if not result:
        candidates = await run_cascade_search(
            extraction,
            transcript_lang=transcript_lang,
            browser_lang=browser_lang,
        )
        if candidates:
            result = await rerank(extraction, candidates)
            candidate_alternatives = _make_candidate_alternatives(
                candidates,
                result,
                max_items=4,
                )
            opinions.append(make_opinion(result, "popularity_guess" if result.get("is_guess") else "cascade"))
            if not result or not result.get("id"):
                result = {
                    "meilleur_titre": candidates[0].get("title") or candidates[0].get("name", "Inconnu"),
                    "id":             candidates[0]["id"],
                    "score":          35,
                    "media_type":     candidates[0].get("media_type", "movie"),
                }
        # ── 6a+. Corroboration par web léger ─────────────────────────
    if result and result_supported_by_web_light(result, extraction):
        web_light_score = min(92, max(result.get("score", 0), 70) + 5)
        web_light_result = {
            **result,
            "score": web_light_score,
            "raison": "corroboration web léger",
        }
        opinions.append(make_opinion(web_light_result, "web_light"))
        print(
            f"🌐 Web light corrobore {result.get('meilleur_titre')} "
            f"→ opinion score={web_light_score}",
            flush=True,
        )

    # ── 6b. Wikidata fallback ─────────────────────────────────────
    current_score = result.get("score", 0) if result else 0
    if should_trigger_wikidata(current_score, extraction, ocr_text or ""):
        print("🌐 Déclenchement Wikidata fallback...", flush=True)
        wd_candidates = await wikidata_search_candidates(
            extraction,
            ocr_text=ocr_text or "",
            browser_lang=browser_lang,
        )
        if wd_candidates:
            print(f"🌐 Wikidata → {len(wd_candidates)} candidats TMDB", flush=True)
            merged_wd = wd_candidates + [
                c for c in candidates if c.get("id") not in {w.get("id") for w in wd_candidates}
            ]
            wd_result = await rerank(extraction, merged_wd)
            opinions.append(make_opinion(wd_result, "wikidata"))
            if wd_result and wd_result.get("score", 0) > current_score:
                print(
                    f"✅ Wikidata améliore le score: {current_score} → {wd_result['score']}",
                    flush=True
                )
                result        = wd_result
                candidates    = merged_wd
                current_score = wd_result["score"]
            elif wd_result and not result:
                result        = wd_result
                candidates    = merged_wd
                current_score = wd_result.get("score", 0)

    # ── 6c. Web search fallback ───────────────────────────────────
    if should_trigger_web_fallback(current_score, candidates, extraction, ocr_text or ""):
        print("🌐 Déclenchement web search fallback...", flush=True)
        web_candidates = await web_search_fallback(
            extraction,
            ocr_text=ocr_text or "",
            browser_lang=browser_lang,
        )
        if web_candidates:
            print(f"🌐 Web search → {len(web_candidates)} candidats TMDB supplémentaires", flush=True)
            merged_candidates = web_candidates + [
                c for c in candidates if c.get("id") not in {w.get("id") for w in web_candidates}
            ]
            web_result = await rerank(extraction, merged_candidates)
            opinions.append(make_opinion(web_result, "web"))
            if web_result and web_result.get("score", 0) > current_score:
                print(
                    f"✅ Web fallback améliore le score: "
                    f"{current_score} → {web_result['score']}",
                    flush=True
                )
                result     = web_result
                candidates = merged_candidates
            elif web_result and not result:
                result     = web_result
                candidates = merged_candidates

    # ── 6d. Score composite + classement multi-candidats ──────────
  
    ranked = rank_opinions(opinions, max_results=5)

    alternatives = []
    if ranked:
        top = ranked[0]
        if not result or top["score"] > result.get("score", 0):
            result = {
            "id":             top["id"],
            "meilleur_titre": top["meilleur_titre"],
            "media_type":     top["media_type"],
            "score":          top["score"],
        }

    # Alternatives issues des sources indépendantes : cascade, web, Wikidata, quote...
        alternatives = ranked[1:]

# Alternatives issues des candidats TMDB, façon Shazam
    if candidates and result:
        candidate_alternatives = _make_candidate_alternatives(
            candidates,
            result,
            max_items=4,
    )

# Fusion propre : alternatives sources + alternatives TMDB
    seen_alt_ids = {result.get("id")} if result else set()
    merged_alternatives = []

    for alt in (alternatives + candidate_alternatives):
        alt_id = alt.get("id")
        if not alt_id or alt_id in seen_alt_ids:
            continue
        seen_alt_ids.add(alt_id)
        merged_alternatives.append(alt)
        if len(merged_alternatives) >= 4:
            break

    alternatives = merged_alternatives

        # ── Sécurité : aucun candidat fiable trouvé ─────────────────
    if not result or not result.get("id"):
        not_found = {
            "status": "not_found",
            "message": (
                "Film non identifié avec certitude. "
                "Aucun candidat fiable n'a été trouvé."
            ),
            "titre_gemini": (
                extraction.get("titres_possibles", [""])[0]
                if extraction.get("titres_possibles")
                else ""
            ),
            "search_youtube": "",
        }

        set_cache(
            url,
            not_found,
            transcript=transcript or "",
            ocr_text=ocr_text or "",
        )

        return not_found

    # ── 7. Finalisation (détails TMDB + construction du résultat) ──
    final = await _finalize_with_known_result(
        url, lang, browser_lang, transcript, ocr_text,
        fake_score=fake_score, result=result, candidates=candidates,
        alternatives=alternatives,
    )

   # ── 8. Enregistrement de la signature embeddings (si succès fiable) ──
    if final.get("status") == "success" and final.get("tmdb_id"):
        await store_film_signature(
            tmdb_id=final["tmdb_id"],
            confidence=final.get("confidence", 0),
            media_type=final.get("media_type", "movie"),
            lang=lang,
            transcript=transcript or "",
            ocr_text=ocr_text or "",
            frame_paths=frames or [],
        )

    # ── 9. Snapshot des candidats pour futurs signalements (non bloquant) ──
    if candidates:
        try:
            combined_text = f"{transcript or ''} {ocr_text or ''}".strip()
            content_hash_fb = key_content(combined_text, lang)
            save_candidates_snapshot(content_hash_fb, candidates)
            save_extraction_snapshot(content_hash_fb, extraction)
        except Exception as e:
            print(f"⚠️ Snapshot feedback KO (non bloquant): {e}", flush=True)

    return final




def _should_show_shazam_choices(
    result: dict,
    alternatives: list,
    hard_threshold: int = 88,
    close_gap: int = 12,
) -> bool:
    if not result:
        return False

    score = result.get("score", 0)

    if score < hard_threshold:
        return True

    if alternatives:
        best_alt_score = max((a.get("score", 0) for a in alternatives), default=0)
        if best_alt_score and (score - best_alt_score) <= close_gap:
            return True

    return False
# ════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    cache_key = f"trending:{lang}:{type}"
    cached = cache_get_generic(cache_key)
    if cached:
        return cached
    try:
        results = await get_trending(lang, media_type=type)
        if not results:
            return {"status": "error", "message": "Aucun résultat disponible."}
        response = {"status": "success", "results": results}
        cache_set_generic(cache_key, response, ttl=21600)  # 6 h
        return response
    except Exception:
        return {"status": "error", "message": "Impossible de charger les tendances."}


@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1, type: str = "movie"):
    GENRE_MAP = {
        "horror": 27, "horreur": 27, "action": 28, "comedy": 35, "comédie": 35,
        "science-fiction": 878, "scifi": 878, "romance": 10749, "animation": 16,
        "thriller": 53, "drama": 18, "drame": 18, "documentary": 99,
        "documentaire": 99, "fantasy": 14, "fantastique": 14,
        "crime": 80, "family": 10751, "famille": 10751,
    }
    genre_id = GENRE_MAP.get(genre_name.lower())
    if not genre_id:
        return {"status": "error", "message": f"Genre '{genre_name}' introuvable."}
    page = min(max(1, page), 500) 

    cache_key = f"discover:{genre_name.lower()}:{lang}:{type}:{page}"
    cached = cache_get_generic(cache_key)           # ← plus de await
    if cached:
        return cached
    try:
        data = await discover_by_genre(genre_id, lang, page, media_type=type)
        response = {"status": "success", **data}
        cache_set_generic(cache_key, response, ttl=21600)   # ← plus de await
        return response
    except Exception:
        return {"status": "error", "message": "Erreur lors du chargement du genre."}






# Provider IDs TMDB 
_PROVIDER_IDS = {
    "amazon":   119,    # Amazon Prime Video
    "netflix":  8,
    "disney":   337,
    "apple":    350,
    "paramount": 531,
    "hulu":     15,
}

@app.get("/discover-provider/{provider_key}")

async def discover_provider(provider_key: str, browser_lang: str = "fr", page: int = 1):
    provider_id = _PROVIDER_IDS.get(provider_key.lower())
    if not provider_id:
        return {"status": "error", "message": f"Plateforme '{provider_key}' inconnue."}
    
    page = min(max(1, page), 500)

    region = _get_region_from_lang(browser_lang)
    cache_key = f"provider:{provider_key.lower()}:{browser_lang}:{page}"

    cached = cache_get_generic(cache_key)
    if cached:
        return cached

    try:
        from data.tmdb import discover_by_provider
        data = await discover_by_provider(provider_id, region, browser_lang, page)
        response = {"status": "success", **data}
        cache_set_generic(cache_key, response, ttl=21600)
        return response
    except Exception as e:
        print(f"❌ discover_provider error: {e}", flush=True)
        return {"status": "error", "message": "Erreur lors du chargement de la plateforme."}

# ════════════════════════════════════════════════════════════════
# ROUTE : Lieux de tournage
# ════════════════════════════════════════════════════════════════
@app.get("/movie/{movie_id}/locations")
async def get_locations(movie_id: int, type: str = "movie"):
    """
    Retourne les lieux de tournage d'un film avec coordonnées GPS.
    Source : Wikidata (P915 + P625).

    Réponse :
      {
        "status": "success",
        "locations": [
          {"name": "Château de Pierrefonds", "lat": 49.35, "lng": 2.98, "wikidata_id": "Q1234"},
          {"name": "Pinewood Studios",        "lat": 51.55, "lng": -0.54, "wikidata_id": "Q5678"},
        ]
      }

    Utilisation frontend :
      - Carte Leaflet/Mapbox affichant les marqueurs GPS
      - Liens vers Google Maps / Wikipedia du lieu
      - SEO : "Films tournés à Paris", "Décors réels de [Film]"

    Monétisation :
      - Liens affiliés vers hôtels/tours à proximité (TripAdvisor, Booking.com)
      - Contenu SEO long tail "where was X filmed"
      - Feature premium : notifications "ce film a été tourné près de vous"
    """
    try:
        from core.wikidata import get_filming_locations
        locations = await get_filming_locations(movie_id, type)
        return {"status": "success", "count": len(locations), "locations": locations}
    except Exception as e:
        print(f"❌ /locations: {e}", flush=True)
        return {"status": "error", "message": "Lieux de tournage indisponibles.", "locations": []}



@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    cache_key = f"movie:{type}:{movie_id}:{lang}"
    cached = cache_get_generic(cache_key)           # ← plus de await
    if cached:
        return cached
    try:
        data = (
            await get_tv_details(movie_id, lang)
            if type == "tv"
            else await get_movie_details(movie_id, lang)
        )
        cache_set_generic(cache_key, data, ttl=86400)   # ← plus de await
        return data
    except Exception:
        return {"status": "error", "message": "Fiche film introuvable."}


@app.get("/tv/{series_id}/season/{season_number}")
async def get_season(series_id: int, season_number: int, lang: str = "fr"):
    try:
        return await get_season_details(series_id, season_number, lang)
    except Exception:
        return {"status": "error", "message": "Saison introuvable."}

@app.get("/rechercher")
async def rechercher(query: str, lang: str = "fr"):
    try:
        movies = await search_candidates(query, lang) or []
        try:
            tv = await search_tv_candidates(query, lang) or []
        except Exception:
            tv = []
        merged = sorted(
            movies + tv,
            key=lambda x: x.get("popularity", 0),
            reverse=True
        )[:20]
        return {"status": "success", "results": merged}
    except Exception:
        return {"status": "error", "message": "Erreur lors de la recherche.", "results": []}


class FeedbackRequest(BaseModel):
    url:                   str
    transcript:            str = ""
    ocr_text:              str = ""
    reported_wrong_id:     Optional[int] = None
    corrected_tmdb_id:     int
    corrected_media_type:  str = "movie"
    lang:                  str = "fr"


@app.post("/feedback/correction")
async def feedback_correction(req: FeedbackRequest, request: Request):
    ip = _get_client_ip(request)
    rate_err = _check_rate_limit(ip)
    if rate_err:
        return rate_err

    combined_text = f"{req.transcript or ''} {req.ocr_text or ''}".strip()
    content_hash = key_content(combined_text, req.lang)

    result = await submit_feedback(
        url=normalize_url(req.url),
        content_hash=content_hash,
        transcript=req.transcript,
        ocr_text=req.ocr_text,
        reported_wrong_id=req.reported_wrong_id,
        corrected_tmdb_id=req.corrected_tmdb_id,
        corrected_media_type=req.corrected_media_type,
        ip=ip,
        lang=req.lang,
    )
    return result



@app.get("/cache-stats")
async def get_cache_stats():
    return cache_stats()

@app.get("/sitemap.xml")
async def sitemap():
    base = "https://pelify.app"
    genres = ["horror","action","comedy","science-fiction","romance",
              "animation","thriller","drama","crime","documentary","fantasy","family"]
    providers = ["netflix","amazon","disney","apple","paramount","hulu"]
    langs = ["fr","en","es","de","zh"]

    urls = [f"{base}/"]
    urls += [f"{base}/{l}" for l in langs]
    urls += [f"{base}/genre/{g}" for g in genres]
    urls += [f"{base}/plateforme/{p}" for p in providers]
    urls += [f"{base}/series", f"{base}/lieux-de-tournage"]

    try:
        cat = getattr(filming_catalogue, "_CATALOGUE", None) \
              or getattr(filming_catalogue, "CATALOGUE", None) or []
        seen = set()
        for film in cat:
            fid = film.get("tmdb_id")
            if not fid or fid in seen:
                continue
            seen.add(fid)
            slug = re.sub(r"[^a-z0-9]+", "-", (film.get("title") or "").lower()).strip("-")
            urls.append(f"{base}/film/{fid}" + (f"/{slug}" if slug else ""))
            if len(seen) >= 5000:
                break
    except Exception as e:
        print(f"⚠️ sitemap films: {e}", flush=True)

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"  <url><loc>{u}</loc></url>\n"
    xml += "</urlset>"
    return Response(content=xml, media_type="application/xml")
@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\n"
        "Sitemap: https://pelify.app/sitemap.xml\n"
    )

@app.get("/")
async def index():
    return FileResponse("frontend/index.html")

@app.get("/health")
async def health():
    return Response(status_code=200)

@app.get("/cache-debug")
async def cache_debug():
    from storage.cache_engine.cache_manager import cache_stats, ram_items
    from storage.cache_engine.redis_client import get_redis
    
    stats = cache_stats()
    
    # Aperçu des 20 premières clés RAM
    ram_preview = [
        {
            "key": k,
            "type": type(v.get("data")).__name__,
            "expires": v.get("expires"),
        }
        for k, v in list(ram_items())[:20]
    ]
    
    # Aperçu des 20 premières clés Redis
    redis_preview = []
    redis_client = get_redis()
    if redis_client:
        try:
            keys = list(redis_client.scan_iter("*", count=20))[:20]
            for k in keys:
                ttl = redis_client.ttl(k)
                redis_preview.append({"key": k, "ttl_seconds": ttl})
        except Exception as e:
            redis_preview = [{"error": str(e)}]
    
    return {
        "stats": stats,
        "ram_preview": ram_preview,
        "redis_preview": redis_preview,
    }

@app.get("/cache-debug/key/{key_type}/{value}")
async def cache_debug_key(key_type: str, value: str, lang: str = "fr"):
    """
    Lit une entrée de cache précise.
    key_type: url | film | title | content_hash
    """
    from storage.cache_engine.cache_manager import cache_get
    from storage.cache_engine.hash_utils import key_url, key_film, key_title
    
    if key_type == "url":
        key = key_url(value)
    elif key_type == "film":
        key = key_film(int(value), lang)
    elif key_type == "title":
        key = key_title(value)
    else:
        key = value  # clé brute
    
    data = cache_get(key)
    return {"key": key, "found": data is not None, "data": data}

@app.get("/genre/{genre_name}")
async def page_genre(genre_name: str):
    return FileResponse("frontend/index.html")

@app.get("/plateforme/{provider_key}")
async def page_plateforme(provider_key: str):
    return FileResponse("frontend/index.html")

@app.get("/film/{film_id}")
async def page_film(film_id: int):
    return FileResponse("frontend/index.html")

@app.get("/film/{film_id}/{slug}")
async def page_film_slug(film_id: int, slug: str):
    return FileResponse("frontend/index.html")

@app.get("/series")
async def page_series():
    return FileResponse("frontend/index.html")

@app.get("/lieux-de-tournage")
async def page_lieux():
    return FileResponse("frontend/index.html")

@app.get("/{lang}")
async def page_multilingue(lang: str):
    if len(lang) != 2 or not lang.isalpha():
        return Response(status_code=404)
    return FileResponse("frontend/index.html")