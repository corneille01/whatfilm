import os
import uuid
import shutil
import subprocess
import traceback
import base64
import time
import asyncio
import re
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vision.scene_detection import extract_keyframes
from vision.universal_downloader import download_video
from vision.ocr_engine import extract_text_from_images, start_loading
from vision.whisper_engine import transcribe

from core.extraction import multimodal_extract
from core.retrieval import build_cascade_queries, build_candidates_from_actors
from data.tmdb import (
    search_candidates, get_movie_details, get_tv_details,
    discover_by_genre, get_trending,
    search_tv_candidates, get_season_details,
)
from data.fake_detector import detect_fake
from core.reranker import rerank
from storage.cache import (
    get_cache, get_cache_by_content, get_cache_by_film,
    get_cache_by_title,
    set_cache, purge_expired, cache_stats
)

# ════════════════════════════════════════════════════════════════
# NORMALISATION D'URL
# ════════════════════════════════════════════════════════════════
_TRACKING_PARAMS = {
    "_r", "_t", "s", "t", "utm_source", "utm_medium", "utm_campaign",
    "utm_content", "utm_term", "fbclid", "igshid", "ref",
    "is_from_webapp", "is_copy_url", "sender_device", "q"
}

def normalize_url(url: str) -> str:
    url = url.strip()
    if "?" not in url:
        return url
    base, qs = url.split("?", 1)
    kept = []
    for part in qs.split("&"):
        if "=" in part:
            key = part.split("=")[0]
            if key not in _TRACKING_PARAMS:
                kept.append(part)
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
        print(f"⚠️ Résolution URL échouée: {e}", flush=True)
        return url

# ════════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT — PREMIÈRE MINUTE UNIQUEMENT
# ════════════════════════════════════════════════════════════════
MAX_VIDEO_SECONDS = 120
MAX_FILE_SIZE_MB  = 50

# ── RATE LIMITING ────────────────────────────────────────────────
from collections import defaultdict

_ip_minute: dict = defaultdict(list)
_ip_day: dict    = defaultdict(list)

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

# ── APP ───────────────────────────────────────────────────────────
async def purge_cache_loop():
    while True:
        await asyncio.sleep(3600)
        purge_expired()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(cleanup_sessions())
    asyncio.create_task(purge_cache_loop())
    start_loading()
    print("✅ ShadowFrame démarré", flush=True)
    yield

app = FastAPI(title="ShadowFrame", lifespan=lifespan)
_analysis_semaphore = asyncio.Semaphore(3)

@app.middleware("http")
async def render_head_fix(request: Request, call_next):
    if request.method == "HEAD":
        return Response(status_code=200)
    return await call_next(request)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

sessions      = {}
SESSION_TIMEOUT = 300

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
        await asyncio.sleep(60)

_trending_cache      = {}
_trending_cache_time = {}
CACHE_DURATION       = 300

class VideoRequest(BaseModel):
    url: str
    lang: str = "fr"

class ContinueRequest(BaseModel):
    session_id: str
    ocr_text:   str = ""
    transcript: str = ""

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "ok"}

def cleanup_files(video_path, audio_path, frame_dir, audio_exists):
    try:
        if os.path.exists(video_path):  os.remove(video_path)
        if audio_exists and os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_dir):   shutil.rmtree(frame_dir)
    except Exception as e:
        print(f"⚠️ Cleanup: {e}", flush=True)

# ════════════════════════════════════════════════════════════════
# ANALYSE PRINCIPALE
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
    print(f"\n📥 ANALYSE [{platform}]: {url[:80]}", flush=True)

    if not SUPPORTED_PLATFORMS.search(url):
        return {"status": "error", "code": "unsupported_platform",
                "message": "Cette plateforme n'est pas supportée. "
                           "Essayez TikTok, Instagram, YouTube, Twitter/X, Facebook ou Dailymotion."}

    # ── Vérification sémaphore : tentative non-bloquante ────────
    # On tente d'acquérir sans bloquer. Si c'est plein → on refuse
    # immédiatement. Sinon on relâche et on re-acquiert proprement
    # via "async with" pour ne pas tenir le slot inutilement.
    if _analysis_semaphore.locked():
        # locked() est True seulement si TOUS les slots sont pris
        # (Semaphore(3).locked() == True quand _value == 0)
        return {"status": "error", "code": "server_busy",
                "message": "Le serveur analyse déjà plusieurs vidéos. Réessayez dans 30 secondes."}

    cached = get_cache(url)
    if cached:
        return {"status": "cached", **cached}

    async with _analysis_semaphore:
        uid        = str(uuid.uuid4())[:8]
        os.makedirs("temp", exist_ok=True)
        video_path = f"temp/{uid}.mp4"
        audio_path = f"temp/{uid}.mp3"
        frame_dir  = f"temp/{uid}"
        audio_exists         = False
        need_client_fallback = False

        try:
            print(f"📥 DOWNLOAD (max {MAX_VIDEO_SECONDS}s) [{platform}]", flush=True)
            dl_result = await download_video(url, video_path, platform)
            if not dl_result["ok"]:
                return {"status": "error", "code": dl_result["code"], "message": dl_result["message"]}

            if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
                return {"status": "error", "code": "download_empty",
                        "message": "Le fichier vidéo est vide ou corrompu."}

            # Conversion si nécessaire
            if video_path.endswith(".mp4"):
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=codec_name",
                         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                        capture_output=True, text=True, timeout=5
                    )
                    codec = probe.stdout.strip()
                    if codec and codec not in ("h264", "hevc", "h265", "avc"):
                        print(f"🔄 Conversion {codec} → h264", flush=True)
                        converted = video_path.replace(".mp4", "_conv.mp4")
                        subprocess.run(
                            ["ffmpeg", "-i", video_path, "-c:v", "libx264",
                             "-crf", "23", "-preset", "fast",
                             "-c:a", "aac", "-y", converted],
                            capture_output=True, timeout=60
                        )
                        if os.path.exists(converted) and os.path.getsize(converted) > 1000:
                            os.remove(video_path)
                            os.rename(converted, video_path)
                except Exception as e:
                    print(f"⚠️ Probe/convert: {e}", flush=True)

            try:
                dur_probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                    capture_output=True, text=True, timeout=5
                )
                duration = float(dur_probe.stdout.strip() or 0)
                if 0 < duration < 3:
                    return {"status": "error", "code": "video_too_short",
                            "message": f"Vidéo trop courte ({duration:.1f}s). Essayez un extrait d'au moins 3 secondes."}
                print(f"✅ Durée: {duration:.1f}s", flush=True)
            except Exception:
                pass

            file_mb = os.path.getsize(video_path) / 1024 / 1024
            print(f"✅ Vidéo téléchargée ({file_mb:.1f} MB)", flush=True)

            # Extraction audio
            print("🎵 AUDIO", flush=True)
            try:
                subprocess.run(
                    ["ffmpeg", "-i", video_path,
                     "-t", str(MAX_VIDEO_SECONDS),
                     "-vn", "-acodec", "mp3",
                     "-ar", "16000",
                     "-ac", "1",
                     "-b:a", "64k",
                     "-y", audio_path],
                    check=True, capture_output=True, timeout=30
                )
                audio_exists = os.path.exists(audio_path) and os.path.getsize(audio_path) > 100
            except Exception as e:
                print(f"⚠️ Audio extraction: {e}", flush=True)

            # Extraction frames
            print("🖼️ FRAMES", flush=True)
            try:
                frames = extract_keyframes(video_path, frame_dir, max_frames=6) or []
            except Exception as e:
                print(f"⚠️ Keyframes: {e}", flush=True)
                frames = []
            frames = [f for f in frames if os.path.exists(f) and os.path.getsize(f) > 0]
            print(f"✅ Frames valides: {len(frames)}", flush=True)

            if not frames and not audio_exists:
                return {"status": "error", "code": "no_frames",
                        "message": "Impossible d'extraire des images ou de l'audio de cette vidéo."}

            # Transcription
            print("🎙️ TRANSCRIPTION", flush=True)
            transcript = ""
            if audio_exists:
                try:
                    transcript = transcribe(audio_path, enabled=True)
                    if transcript:
                        print(f"✅ Transcription OK ({len(transcript)} chars)", flush=True)
                    else:
                        print("⚠️ Transcription vide → fallback client", flush=True)
                except Exception as e:
                    print(f"⚠️ Transcription KO: {e}", flush=True)
            else:
                print("⚠️ Pas d'audio → fallback client", flush=True)

            need_client_fallback = not bool(transcript)

            if need_client_fallback:
                print("🔄 Fallback client (Tesseract.js + Whisper.js)", flush=True)
                frames_b64 = []
                for fpath in frames:
                    try:
                        with open(fpath, "rb") as f:
                            frames_b64.append(base64.b64encode(f.read()).decode())
                    except Exception:
                        pass
                audio_b64 = ""
                if audio_exists:
                    try:
                        with open(audio_path, "rb") as f:
                            audio_b64 = base64.b64encode(f.read()).decode()
                    except Exception:
                        pass
                session_id = str(uuid.uuid4())[:12]
                sessions[session_id] = {
                    "url": url, "lang": req.lang,
                    "video_path": video_path, "audio_path": audio_path,
                    "frame_dir": frame_dir, "ocr_text": "",
                    "timestamp": time.time()
                }
                return {
                    "status":        "transcription_needed",
                    "session_id":    session_id,
                    "frames_base64": frames_b64,
                    "audio_base64":  audio_b64
                }

            return await process_analysis(frames, "", transcript, url, req.lang)

        except asyncio.TimeoutError:
            return {"status": "error", "code": "timeout",
                    "message": "L'analyse a pris trop de temps. Réessayez avec une vidéo plus courte."}
        except Exception as e:
            print(f"❌ ERROR: {traceback.format_exc()}", flush=True)
            return {"status": "error", "code": "unexpected",
                    "message": "Une erreur inattendue s'est produite. Réessayez dans quelques instants."}
        finally:
            if not need_client_fallback:
                cleanup_files(video_path, audio_path, frame_dir, audio_exists)

# ── ANALYSE CONTINUE ──────────────────────────────────────────────
@app.post("/analyser_continue")
async def analyser_continue(req: ContinueRequest):
    session = sessions.get(req.session_id)
    if not session:
        return {"status": "error", "code": "session_expired",
                "message": "Session expirée. Relancez l'analyse."}
    try:
        ocr_text   = req.ocr_text or ""
        transcript = req.transcript or ""
        frame_dir  = session["frame_dir"]
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
        return await process_analysis(frames_paths, ocr_text, transcript, session["url"], session["lang"])
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
# PROCESS ANALYSIS
# ════════════════════════════════════════════════════════════════
async def process_analysis(frames, ocr_text, transcript, url, lang):
    """
    Pipeline complet :
    1. Cache contenu
    2. Détection script
    3. Extraction multimodale (LLM)
    4. Cache titre
    5. Recherche via acteurs (filmographie) → rerank
    6. Fallback : recherche textuelle TMDB → rerank
    7. Détails TMDB + réponse finale
    """

    # ── 1. Cache niveau contenu ──────────────────────────────────
    if transcript or ocr_text:
        content_hit = get_cache_by_content(transcript, ocr_text, lang)
        if content_hit:
            set_cache(url, content_hit, transcript=transcript, ocr_text=ocr_text)
            return {"status": "cached", **content_hit}

    # ── 2. Détection script ──────────────────────────────────────
    combined_text  = (transcript or "") + " " + (ocr_text or "")
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

    # ── 3. Extraction multimodale ────────────────────────────────
    extraction = await multimodal_extract(frames, ocr_text, transcript) or {}
    if detected_script != "latin":
        extraction["detected_script"] = detected_script
    extraction["_transcript_raw"] = transcript or ""

    # ── 4. Cache niveau titre ────────────────────────────────────
    for titre_candidat in extraction.get("titres_possibles", []):
        if str(titre_candidat).startswith("?"):
            continue
        title_hit = get_cache_by_title(titre_candidat, lang)
        if title_hit:
            set_cache(url, title_hit, transcript=transcript, ocr_text=ocr_text)
            return {"status": "cached", **title_hit}

    fake_score  = detect_fake((ocr_text or "") + " " + (transcript or ""))
    candidates  = []
    search_type = "movie"
    result      = None

    # ── 5. Recherche via acteurs (filmographie) ──────────────────
    actor_candidates = await build_candidates_from_actors(extraction, lang)
    if actor_candidates:
        print(f"🎭 Recherche via acteurs: {len(actor_candidates)} candidats", flush=True)
        actor_result = await rerank(extraction, actor_candidates)
        if actor_result and actor_result.get("score", 0) >= 50:
            matched_candidate = next(
                (c for c in actor_candidates if c.get("id") == actor_result.get("id")),
                None
            )
            if matched_candidate:
                actor_result["media_type"] = matched_candidate.get("media_type", "movie")
            result      = actor_result
            candidates  = actor_candidates
            search_type = actor_result.get("media_type", "movie")
            print(
                f"✅ Acteur-match retenu (score={result['score']}, type={search_type})",
                flush=True
            )

    # ── 6. Fallback : recherche textuelle TMDB ───────────────────
    if not result:
        queries = await build_cascade_queries(extraction)

        if detected_script in ("chinese", "japanese", "korean"):
            lang_map      = {"chinese": "zh", "japanese": "ja", "korean": "ko"}
            original_lang = lang_map[detected_script]
            titre_brut    = extraction.get("titre", "") or ""
            if titre_brut and original_lang != lang:
                queries = queries + [f"{titre_brut} {original_lang}"]

        genre_detected = (extraction.get("genre_apparent") or "").lower()

        TV_FIRST = {
            "anime", "serie", "série", "animation",
            "série-animation", "série-animée",
        }
        BOTH = {
            "documentaire", "documentary",
            "documentaire-série", "docu-série",
        }

        async def _try_movie(q, lg):
            try:
                r = await search_candidates(q, lg)
                for c in r: c.setdefault("media_type", "movie")
                return r
            except Exception:
                return []

        async def _try_tv(q, lg):
            try:
                r = await search_tv_candidates(q, lg)
                for c in r: c.setdefault("media_type", "tv")
                return r
            except Exception:
                return []

        async def _try_both(q, lg):
            rm, rt = await asyncio.gather(_try_movie(q, lg), _try_tv(q, lg))
            merged = rm + rt
            return sorted(merged, key=lambda x: x.get("popularity", 0), reverse=True)

        for search_lang in ([lang] + (["en"] if lang != "en" else [])):
            for q in queries:
                if genre_detected in BOTH:
                    res = await _try_both(q, search_lang)
                    if res:
                        candidates  = res
                        search_type = "mixed"
                        break
                elif genre_detected in TV_FIRST:
                    res = await _try_tv(q, search_lang)
                    if not res:
                        res = await _try_movie(q, search_lang)
                        if res: search_type = "movie"
                    else:
                        search_type = "tv"
                    if res:
                        candidates = res
                        break
                else:
                    res = await _try_movie(q, search_lang)
                    if not res:
                        res = await _try_tv(q, search_lang)
                        if res: search_type = "tv"
                    else:
                        search_type = "movie"
                    if res:
                        candidates = res
                        break
            if candidates:
                break

        if not candidates:
            titres = extraction.get("titres_possibles", [])
            titre  = str(titres[0]).lstrip("?") if titres else ""
            not_found = {
                "status":         "not_found",
                "message":        "Aucun film ou série trouvé pour cette vidéo.",
                "search_youtube": f"https://www.youtube.com/results?search_query={titre}+film",
                "search_google":  f"https://www.google.com/search?q={titre}+film",
                "search_tmdb":    f"https://www.themoviedb.org/search?query={titre}",
            }
            set_cache(url, not_found, transcript=transcript or "", ocr_text=ocr_text or "")
            return not_found

        result = await rerank(extraction, candidates)
        if not result or not result.get("id"):
            result = {
                "meilleur_titre": candidates[0].get("title", "Inconnu"),
                "id":             candidates[0]["id"],
                "score":          35,
                "media_type":     search_type,
            }

    # ── 7. Score de confiance et cache film ──────────────────────
    confidence = result.get("score", 0)

    if confidence >= 30 and result.get("id"):
        film_hit = get_cache_by_film(result["id"], lang)
        if film_hit:
            set_cache(url, film_hit, transcript=transcript or "", ocr_text=ocr_text or "")
            return {"status": "cached", **film_hit}

    if confidence < 30:
        titre    = result.get("meilleur_titre", "")
        low_conf = {
            "status":         "not_found",
            "message":        f"Film non identifié avec certitude ({confidence}%). Essayez de rechercher manuellement.",
            "titre_gemini":   titre,
            "search_youtube": f"https://www.youtube.com/results?search_query={titre}+film+trailer",
            "search_google":  f"https://www.google.com/search?q={titre}+film",
            "search_tmdb":    f"https://www.themoviedb.org/search?query={titre}",
        }
        set_cache(url, low_conf, transcript=transcript or "", ocr_text=ocr_text or "")
        return low_conf

    # ── 8. Détails TMDB ──────────────────────────────────────────
    movie_id = result["id"]

    effective_type = result.get("media_type") or search_type
    if effective_type == "mixed":
        matched = next(
            (c for c in candidates if c.get("id") == result.get("id")), None
        )
        effective_type = matched.get("media_type", "movie") if matched else "movie"

    print(f"📋 Détails TMDB id={movie_id} type={effective_type}", flush=True)

    try:
        details = (
            await get_tv_details(movie_id, lang)
            if effective_type == "tv"
            else await get_movie_details(movie_id, lang)
        )
    except Exception:
        try:
            if effective_type == "tv":
                print(f"⚠️ get_tv_details KO id={movie_id} → essai movie", flush=True)
                details = await get_movie_details(movie_id, lang)
                effective_type = "movie"
            else:
                print(f"⚠️ get_movie_details KO id={movie_id} → essai tv", flush=True)
                details = await get_tv_details(movie_id, lang)
                effective_type = "tv"
        except Exception as e2:
            print(f"❌ TMDB KO id={movie_id}: {e2}", flush=True)
            return {"status": "error", "code": "tmdb_error",
                    "message": "Impossible de récupérer les détails du film."}

    region    = {"fr": "FR", "en": "US", "es": "ES", "de": "DE", "zh": "CN"}.get(lang, "FR")
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
        "title":           result.get("meilleur_titre") or details.get("title") or details.get("name") or "Inconnu",
        "confidence":      max(0, confidence),
        "synopsis":        details.get("overview", ""),
        "image":           f"https://image.tmdb.org/t/p/w500{details['poster_path']}" if details.get("poster_path") else "",
        "streaming":       [p.get("provider_name") for p in providers],
        "streaming_logos": [{"name": p.get("provider_name"), "logo_path": p.get("logo_path")} for p in providers],
        "similar":         [
            {"title": s.get("title", s.get("name", "?")), "id": s.get("id"), "poster_path": s.get("poster_path")}
            for s in details.get("similar", {}).get("results", [])[:6]
        ],
        "cast":            [
            {"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")}
            for c in details.get("credits", {}).get("cast", [])[:8]
        ],
        "trailer":         "",
        "genres":          [g["name"] for g in details.get("genres", [])],
        "year":            (details.get("release_date") or details.get("first_air_date") or "").split("-")[0],
        "runtime":         details.get("runtime") or (details.get("episode_run_time") or [None])[0],
        "vote_average":    details.get("vote_average"),
        "vote_count":      details.get("vote_count"),
        "tmdb_id":         movie_id,
        "lang":            lang,
        "is_fake":         fake_score > 70,
        "seasons":         details.get("seasons") if is_series else None,
    }

    if confidence >= 50:
        set_cache(url, final, transcript=transcript or "", ocr_text=ocr_text or "")

    return final

# ── ROUTES PUBLIQUES ──────────────────────────────────────────────
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    cache_key = f"{lang}_{type}"
    now = time.time()
    if cache_key in _trending_cache and (now - _trending_cache_time.get(cache_key, 0)) < CACHE_DURATION:
        return _trending_cache[cache_key]
    try:
        results = await get_trending(lang, media_type=type)
        if not results:
            return {"status": "error", "message": "Aucun résultat disponible."}
        response = {"status": "success", "results": results}
        _trending_cache[cache_key] = response
        _trending_cache_time[cache_key] = now
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
    try:
        data = await discover_by_genre(genre_id, lang, page, media_type=type)
        return {"status": "success", **data}
    except Exception:
        return {"status": "error", "message": "Erreur lors du chargement du genre."}

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    try:
        return await get_tv_details(movie_id, lang) if type == "tv" else await get_movie_details(movie_id, lang)
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
        merged = sorted(movies + tv, key=lambda x: x.get("popularity", 0), reverse=True)[:20]
        return {"status": "success", "results": merged}
    except Exception:
        return {"status": "error", "message": "Erreur lors de la recherche.", "results": []}

@app.get("/cache-stats")
async def get_cache_stats():
    return cache_stats()

@app.get("/sitemap.xml")
async def sitemap():
    base = "https://quelfilm.app"
    urls = [f"{base}/", f"{base}/fr", f"{base}/en", f"{base}/es", f"{base}/de", f"{base}/zh"]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"  <url><loc>{u}</loc></url>\n"
    xml += "</urlset>"
    return HTMLResponse(content=xml, media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: https://quelfilm.app/sitemap.xml\n")

@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")