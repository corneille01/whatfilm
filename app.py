import os
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

from core import extraction
from routes_filming import router as filming_router
from typing import Optional
from contextlib import asynccontextmanager
from collections import defaultdict
from storage.cache_engine.lock_manager import acquire_lock, release_lock

from fastapi import FastAPI, Request, UploadFile, File, Form



from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.web_search import should_trigger_web_fallback, web_search_fallback
from core.wikidata import wikidata_search_candidates, should_trigger_wikidata, get_wikidata_enrichment, get_filming_locations
from core import filming_catalogue


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
from core.reranker import rerank
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
GEMINI_MAX_SECONDS = 60   # durée max envoyée à Gemini (coût + vitesse)
MAX_FILE_SIZE_MB  = 50

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
_analysis_semaphore = asyncio.Semaphore(3)


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

# ════════════════════════════════════════════════════════════════
# TÂCHE DE FOND : download + analyse complète
# ════════════════════════════════════════════════════════════════
async def _process_local_file(
    session: dict, video_path: str, audio_path: str, frame_dir: str,
    url_label: str, lang: str, browser_lang: str,
) -> bool:
    """
    Fichier vidéo LOCAL (téléchargé OU uploadé) :
      1) conversion codec + validation durée
      2) Gemini sur la vidéo (tronquée à GEMINI_MAX_SECONDS) → si concluant : terminé
      3) sinon : audio + frames + transcription → process_analysis
      4) si aucune frame : transcription_needed (fallback client)
    Retourne True si un fallback client est en attente (ne pas nettoyer les fichiers).
    """
    audio_exists = False
    session["status"] = "processing"

    # 1) Conversion codec
    if video_path.endswith(".mp4"):
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_name",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=5)
            codec = probe.stdout.strip()
            if codec and codec not in ("h264", "hevc", "h265", "avc"):
                converted = video_path.replace(".mp4", "_conv.mp4")
                subprocess.run(
                    ["ffmpeg", "-i", video_path, "-c:v", "libx264", "-crf", "23",
                     "-preset", "fast", "-c:a", "aac", "-y", converted],
                    capture_output=True, timeout=60)
                if os.path.exists(converted) and os.path.getsize(converted) > 1000:
                    os.remove(video_path); os.rename(converted, video_path)
        except Exception as e:
            print(f"⚠️ Probe/convert: {e}", flush=True)

    duration = 0.0
    try:
        dur = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=5)
        duration = float(dur.stdout.strip() or 0)
        if 0 < duration < 3:
            session["status"] = "error"
            session["result"] = {"status": "error", "code": "video_too_short",
                "message": f"Vidéo trop courte ({duration:.1f}s). Essayez au moins 3 secondes."}
            return False
    except Exception:
        pass

    # 2) Gemini sur la vidéo (tronquée à GEMINI_MAX_SECONDS pour le coût + la vitesse)
    gemini_path = video_path
    if duration > GEMINI_MAX_SECONDS:
        try:
            trimmed = video_path.replace(".mp4", f"_g{GEMINI_MAX_SECONDS}.mp4")
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-t", str(GEMINI_MAX_SECONDS),
                 "-c", "copy", "-y", trimmed],
                capture_output=True, timeout=30)
            if os.path.exists(trimmed) and os.path.getsize(trimmed) > 1000:
                gemini_path = trimmed
                print(f"✂️ Tronquée à {GEMINI_MAX_SECONDS}s pour Gemini "
                      f"(vidéo de {duration:.0f}s)", flush=True)
        except Exception as e:
            print(f"⚠️ Troncature KO: {e} → vidéo entière", flush=True)

    print("🎬 Gemini sur la vidéo (fichier)...", flush=True)
    try:
        from core.extraction import _extract_gemini_video_file
        file_ext = await _extract_gemini_video_file(gemini_path)
        if _extraction_is_useful(file_ext):
            print("✅ Gemini fichier concluant → pas de frames", flush=True)
            result = await process_analysis(
                frames=[], ocr_text="", transcript=file_ext.get("_transcript_raw", ""),
                url=url_label, lang=lang, browser_lang=browser_lang,
                prefetched_extraction=file_ext)
            session["status"] = "done"; session["result"] = result
            return False
        print("⚠️ Gemini fichier non concluant → frames + transcription", flush=True)
    except Exception as e:
        print(f"⚠️ Gemini fichier KO: {e} → frames", flush=True)
    finally:
        if gemini_path != video_path and os.path.exists(gemini_path):
            try:
                os.remove(gemini_path)
            except Exception:
                pass

    # 3) Audio
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-t", str(MAX_VIDEO_SECONDS),
             "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
             "-b:a", "64k", "-y", audio_path],
            check=True, capture_output=True, timeout=30)
        audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 100
    except Exception:
        try:
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-t", str(MAX_VIDEO_SECONDS),
                 "-vn", "-ar", "16000", "-ac", "1", "-f", "mp3", "-y", audio_path],
                check=True, capture_output=True, timeout=30)
            audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 100
        except Exception as e2:
            print(f"⚠️ Audio KO: {str(e2)[:80]}", flush=True)

    # 4) Frames
    try:
        frames = extract_keyframes(video_path, frame_dir, max_frames=6) or []
    except Exception as e:
        print(f"⚠️ Keyframes: {e}", flush=True); frames = []
    frames = [f for f in frames if os.path.exists(f) and os.path.getsize(f) > 0]
    print(f"✅ Frames valides: {len(frames)}", flush=True)

    if not frames and not audio_exists:
        session["status"] = "error"
        session["result"] = {"status": "error", "code": "no_frames",
            "message": "Impossible d'extraire des images ou de l'audio de cette vidéo."}
        return False

    # 5) Transcription
    transcript = ""
    if audio_exists:
        try:
            transcript = transcribe(audio_path, enabled=True) or ""
        except Exception as e:
            print(f"⚠️ Transcription KO: {e}", flush=True)

    # 6) Analyse via frames
    if frames:
        result = await process_analysis(frames, "", transcript, url_label, lang, browser_lang)
        session["status"] = "done"; session["result"] = result
        return False

    # 7) Fallback client (aucune frame)
    audio_b64 = ""
    if audio_exists:
        try:
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
        except Exception:
            pass
    fallback_sid = str(uuid.uuid4())[:12]
    sessions[fallback_sid] = {
        "url": url_label, "lang": lang, "browser_lang": browser_lang,
        "video_path": video_path, "audio_path": audio_path, "frame_dir": frame_dir,
        "ocr_text": "", "timestamp": time.time()}
    session["status"] = "done"
    session["result"] = {"status": "transcription_needed", "session_id": fallback_sid,
                         "frames_base64": [], "audio_base64": audio_b64}
    return True






async def _run_download_and_analyse(session_id, url, platform, lang, browser_lang):
    session = _dl_sessions.get(session_id)
    if not session:
        return
    video_path = session["video_path"]; audio_path = session["audio_path"]; frame_dir = session["frame_dir"]
    need_client_fallback = False
    try:
        # URL directe → Gemini (sauf TikTok), pas de download si concluant
        if platform != "tiktok":
            session["status"] = "processing"
            try:
                from core.extraction import _extract_gemini_url_direct
                extraction = await _extract_gemini_url_direct(url)
                if _extraction_is_useful(extraction):
                    result = await process_analysis(
                        frames=[], ocr_text="", transcript=extraction.get("_transcript_raw", ""),
                        url=url, lang=lang, browser_lang=browser_lang,
                        prefetched_extraction=extraction)
                    session["status"] = "done"; session["result"] = result
                    return
                print(f"⚠️ URL directe non concluante [{platform}] → download", flush=True)
            except Exception as e:
                print(f"⚠️ URL directe exception: {e} → download", flush=True)

        # Download
        session["status"] = "downloading"
        print(f"📥 DOWNLOAD [{platform}] session={session_id}", flush=True)
        dl = await download_video(url, video_path, platform)
        if not dl["ok"]:
            session["status"] = "error"
            session["result"] = {"status": "error", "code": dl["code"], "message": dl["message"]}
            return
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
            session["status"] = "error"
            session["result"] = {"status": "error", "code": "download_empty",
                                 "message": "Le fichier vidéo est vide ou corrompu."}
            return
        print(f"✅ Vidéo téléchargée ({os.path.getsize(video_path)/1024/1024:.1f} MB)", flush=True)

        # Fichier local → Gemini fichier → frames/transcription
        need_client_fallback = await _process_local_file(
            session, video_path, audio_path, frame_dir, url, lang, browser_lang)

    except Exception:
        print(f"❌ _run_download_and_analyse: {traceback.format_exc()}", flush=True)
        session["status"] = "error"
        session["result"] = {"status": "error", "code": "unexpected",
                             "message": "Une erreur inattendue s'est produite. Réessayez."}
    finally:
        if not need_client_fallback:
            cleanup_files(video_path, audio_path, frame_dir, True)
        session["timestamp"] = time.time()

        # Libère le verrou anti-doublons quel que soit le résultat
        # (succès, erreur, ou besoin de fallback client). Garantit que le
        # verrou ne reste jamais bloqué indéfiniment même si une exception
        # imprévue survient plus haut dans le bloc try.
        lock_key = session.get("_lock_key")
        lock_token = session.get("_lock_token")
        if lock_key and lock_token:
            release_lock(lock_key, lock_token)
# ════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL
# ════════════════════════════════════════════════════════════════
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
    lock_token = acquire_lock(lock_key, ttl=120)

    if lock_token is None:
        # Verrou déjà pris par une autre requête en cours sur cette URL.
        # On attend que la première requête finisse (max ~8s par tentative,
        # quelques tentatives), puis on relit le cache plutôt que de
        # dupliquer le pipeline complet.
        for _ in range(8):
            await asyncio.sleep(1)
            cached = get_cache(url)
            if cached:
                print(f"✅ Cache hit après attente verrou: {url[:60]}", flush=True)
                return {"status": "cached", **cached}
        # Toujours pas de cache après l'attente : la première requête est
        # probablement encore en cours (vidéo longue, Gemini lent) ou a
        # échoué silencieusement. On laisse cette requête repartir sur le
        # pipeline normal plutôt que de bloquer indéfiniment l'utilisateur.
        print(f"⚠️ Verrou actif mais pas de cache après attente, on continue normalement: {url[:60]}", flush=True)

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
@app.get("/analyser_status/{session_id}")
async def analyser_status(session_id: str):
    session = _dl_sessions.get(session_id)
    if not session:
        return {"status": "error", "code": "session_expired",
                "message": "Session expirée ou introuvable. Relancez l'analyse."}

    current_status = session.get("status", "queued")
    if current_status in ("queued", "downloading", "processing"):
        return {"status": "processing", "step": current_status}

    result = session.get("result") or {
        "status": "error", "code": "unexpected", "message": "Résultat manquant."
    }
    _dl_sessions.pop(session_id, None)
    return result

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
) -> dict:
    """
    Finalise une analyse à partir d'un résultat déjà connu (match embeddings,
    ou tout autre cas où le rerank a déjà été fait en amont). Reprend la
    logique "Détails TMDB" de process_analysis() sans dupliquer le code.

    Paramètres :
      result     : dict avec au moins {id, media_type, meilleur_titre, score}
      candidates : liste de candidats (peut être minimaliste, juste pour
                   permettre au code de retrouver le media_type si besoin)
    """
    confidence = result.get("score", 0)

    if confidence >= 30 and result.get("id"):
        film_hit = get_cache_by_film(result["id"], lang)
        if film_hit:
            set_cache(url, film_hit, transcript=transcript or "", ocr_text=ocr_text or "")
            return {"status": "cached", **film_hit}

    if confidence < 35:
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

    if confidence >= 50:
        set_cache(url, final, transcript=transcript or "", ocr_text=ocr_text or "")

    return final


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
    # Vérifie si ce texte/ces frames ressemblent à un film déjà identifié
    # avec succès auparavant, AVANT de dépenser du quota Gemini/Qwen/Groq.
    # N'agit que si prefetched_extraction est absent (cas YouTube direct,
    # où l'extraction a déjà eu lieu côté _run_download_and_analyse) et
    # qu'on a du texte ou des frames à comparer. En cas d'échec/absence
    # de configuration université, check_known_film retourne None
    # silencieusement et le pipeline continue normalement plus bas.
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

            # Le film est connu par embeddings mais pas encore en cache fiche
            # complète (rare, ex: cache fiche expiré entre temps) : on continue
            # directement vers "Détails TMDB" via _finalize_with_known_result,
            # sans dépenser de quota LLM sur l'extraction ni sur le rerank.
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
        print("✅ Extraction prefetchée utilisée (YouTube direct)", flush=True)
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
    # Gemini retourne parfois langue_originale="en" pour des films non-anglais
    # quand la transcription contient des mots ambigus.
    # Si browser_lang est une langue latine ET les titres Gemini contiennent
    # des marqueurs de cette langue → forcer transcript_lang = browser_lang.
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

        # Seuil : au moins 2 marqueurs de la langue du navigateur dans les titres/desc
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

    # ── 5. Recherche via acteurs ─────────────────────────────────
    actor_candidates = await build_candidates_from_actors(
        extraction, lang=transcript_lang or browser_lang or lang
    )
    if actor_candidates:
        print(f"🎭 Recherche via acteurs: {len(actor_candidates)} candidats", flush=True)
        actor_result = await rerank(extraction, actor_candidates)
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

    # ── 6. Fallback : cascade TMDB multi-langue ──────────────────
    if not result:
        candidates = await run_cascade_search(
            extraction,
            transcript_lang=transcript_lang,
            browser_lang=browser_lang,
        )
        if candidates:
            result = await rerank(extraction, candidates)
            if not result or not result.get("id"):
                result = {
                    "meilleur_titre": candidates[0].get("title") or candidates[0].get("name", "Inconnu"),
                    "id":             candidates[0]["id"],
                    "score":          35,
                    "media_type":     candidates[0].get("media_type", "movie"),
                }

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

    # ── Aucun résultat ────────────────────────────────────────────
    if not candidates and not result:
        titres    = extraction.get("titres_possibles", [])
        titre     = str(titres[0]).lstrip("?") if titres else ""
        not_found = {
            "status":         "not_found",
            "message":        "Aucun film ou série trouvé pour cette vidéo.",
            "search_youtube": f"https://www.youtube.com/results?search_query={titre}+film",
            "search_google":  f"https://www.google.com/search?q={titre}+film",
            "search_tmdb":    f"https://www.themoviedb.org/search?query={titre}",
        }
        set_cache(url, not_found, transcript=transcript or "", ocr_text=ocr_text or "")
        return not_found

    if not result or not result.get("id"):
        result = {
            "meilleur_titre": candidates[0].get("title") or candidates[0].get("name", "Inconnu"),
            "id":             candidates[0]["id"],
            "score":          35,
            "media_type":     candidates[0].get("media_type", "movie"),
        }

    # ── 7. Finalisation (détails TMDB + construction du résultat) ──
    final = await _finalize_with_known_result(
        url, lang, browser_lang, transcript, ocr_text,
        fake_score=fake_score, result=result, candidates=candidates,
    )

    # ── 8. Enregistrement de la signature embeddings (si succès fiable) ──
    # N'enregistre que si le résultat final est un succès complet avec une
    # confiance suffisante (store_film_signature filtre déjà sur >= 70 en
    # interne, donc cet appel est toujours sûr même en cas de score faible).
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

    return final

# ════════════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ════════════════════════════════════════════════════════════════


# Dans ton router FastAPI
@app.get("/.well-known/security.txt")
async def security_txt():
    return PlainTextResponse("""Contact: mailto:security@pelify.app
Expires: 2027-01-01T00:00:00.000Z
Preferred-Languages: fr, en
""")
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