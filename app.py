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
from collections import defaultdict

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
# TÉLÉCHARGEMENT
# ════════════════════════════════════════════════════════════════
MAX_VIDEO_SECONDS = 60
MAX_FILE_SIZE_MB  = 50

# ── RATE LIMITING ────────────────────────────────────────────────
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

sessions        = {}
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

    if _analysis_semaphore._value == 0:
        return {"status": "error", "code": "server_busy",
                "message": "Le serveur analyse déjà plusieurs vidéos. Réessayez dans 30 secondes."}

    # Cache URL (niveau 1)
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
            # ── Téléchargement ────────────────────────────────────
            print(f"📥 DOWNLOAD (max {MAX_VIDEO_SECONDS}s) [{platform}]", flush=True)
            dl_result = await download_video(url, video_path, platform)

            if not dl_result["ok"]:
                return {"status": "error",
                        "code":   dl_result["code"],
                        "message": dl_result["message"]}

            if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
                return {"status": "error", "code": "download_empty",
                        "message": "Le fichier vidéo est vide ou corrompu."}

            # Conversion codec si nécessaire
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

            # Vérifier durée
            try:
                dur_probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                    capture_output=True, text=True, timeout=5
                )
                duration = float(dur_probe.stdout.strip() or 0)
                if 0 < duration < 3:
                    return {"status": "error", "code": "video_too_short",
                            "message": f"Vidéo trop courte ({duration:.1f}s). "
                                       "Essayez un extrait d'au moins 3 secondes."}
                print(f"✅ Durée: {duration:.1f}s", flush=True)
            except Exception:
                pass

            file_mb = os.path.getsize(video_path) / 1024 / 1024
            print(f"✅ Vidéo téléchargée ({file_mb:.1f} MB)", flush=True)

            # ── Extraction audio ──────────────────────────────────
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

            # ── Extraction frames ─────────────────────────────────
            print("🖼️ FRAMES", flush=True)
            try:
                frames = extract_keyframes(video_path, frame_dir, max_frames=6) or []
            except Exception as e:
                print(f"⚠️ Keyframes: {e}", flush=True)
                frames = []

            frames = [f for f in frames
                      if os.path.exists(f) and os.path.getsize(f) > 0]
            print(f"✅ Frames valides: {len(frames)}", flush=True)

            if not frames and not audio_exists:
                return {"status": "error", "code": "no_frames",
                        "message": "Impossible d'extraire des images ou de l'audio de cette vidéo."}

            # ── Transcription serveur (cascade) ───────────────────
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

            # ── Décision fallback client ──────────────────────────
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

            return await process_analysis(
                frames, "", transcript, url, req.lang)

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

        return await process_analysis(
            frames_paths, ocr_text, transcript,
            session["url"], session["lang"])

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

    # Cache niveau 2 : même contenu, lien différent
    if transcript or ocr_text:
        content_hit = get_cache_by_content(transcript, ocr_text, lang)
        if content_hit:
            set_cache(url, content_hit,
                      transcript=transcript, ocr_text=ocr_text)
            return {"status": "cached", **content_hit}

    # Détecter la langue du contenu
    combined_text = (transcript or "") + " " + (ocr_text or "")
    detected_script = "latin"
    if re.search(r"[؀-ۿ]", combined_text):
        detected_script = "arabic"
    elif re.search(r"[一-鿿㐀-䶿]", combined_text):
        detected_script = "chinese"
    elif re.search(r"[가-힯]", combined_text):
        detected_script = "korean"
    elif re.search(r"[぀-ゟ゠-ヿ]", combined_text):
        detected_script = "japanese"
    elif re.search(r"[Ѐ-ӿ]", combined_text):
        detected_script = "cyrillic"
    if detected_script != "latin":
        print(f"🌐 Script détecté: {detected_script}", flush=True)

    extraction = await multimodal_extract(frames, ocr_text, transcript) or {}

    # ── Injecter le transcript brut pour le croisement acteur×transcript ──
    # retrieval.py extrait les mots-clés du transcript pour re-trier
    # la filmographie d'un acteur reconnu visuellement.
    # Ex: Eddie Murphy (visage) × "bourse Duke" → "Un fauteuil pour deux"
    extraction["_transcript_raw"] = transcript or ""

    if detected_script != "latin":
        extraction["detected_script"] = detected_script

    fake_score = detect_fake((ocr_text or "") + " " + (transcript or ""))

    candidates  = []
    search_type = "movie"

    # ── Priorité 1 : recherche par acteurs reconnus ───────────────
    # Si Gemini a identifié un acteur visuellement, on cherche dans
    # sa filmographie TMDB et on croise avec les mots-clés du transcript.
    # Évite les longues cascades de requêtes texte dans ~60% des cas.
    if extraction.get("acteurs"):
        try:
            actor_candidates = await build_candidates_from_actors(extraction, lang)
            if actor_candidates:
                candidates  = actor_candidates
                search_type = "movie"
                print(f"🎭 Recherche via acteurs: {len(candidates)} candidats",
                      flush=True)
        except Exception as e:
            print(f"⚠️ build_candidates_from_actors: {e}", flush=True)

    # ── Priorité 2 : cascade de requêtes texte ────────────────────
    # Utilisé si aucun acteur reconnu ou si la recherche acteur n'a
    # retourné aucun candidat.
    if not candidates:
        queries = await build_cascade_queries(extraction)

        for q in queries:
            results = await search_candidates(q, lang)
            if results:
                candidates = results
                break

        if not candidates:
            for q in queries:
                try:
                    results = await search_tv_candidates(q, lang)
                    if results:
                        candidates = results
                        search_type = "tv"
                        break
                except Exception:
                    pass

        # Retry en anglais si langue != en
        if not candidates and lang != "en":
            for q in queries[:3]:
                results = await search_candidates(q, "en")
                if results:
                    candidates = results
                    break
            if not candidates:
                for q in queries[:3]:
                    try:
                        results = await search_tv_candidates(q, "en")
                        if results:
                            candidates = results
                            search_type = "tv"
                            break
                    except Exception:
                        pass

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
            "score":          35
        }

    confidence = result.get("score", 0)

    # Cache niveau 3 : film universel (tmdb_id connu)
    if confidence >= 30 and result.get("id"):
        film_hit = get_cache_by_film(result["id"], lang)
        if film_hit:
            set_cache(url, film_hit,
                      transcript=transcript or "",
                      ocr_text=ocr_text or "")
            return {"status": "cached", **film_hit}

    if confidence < 30:
        titre = result.get("meilleur_titre", "")
        low_conf = {
            "status":         "not_found",
            "message":        f"Film non identifié avec certitude ({confidence}%). "
                              "Essayez de rechercher manuellement.",
            "titre_gemini":   titre,
            "search_youtube": f"https://www.youtube.com/results?search_query={titre}+film+trailer",
            "search_google":  f"https://www.google.com/search?q={titre}+film",
            "search_tmdb":    f"https://www.themoviedb.org/search?query={titre}",
        }
        set_cache(url, low_conf, transcript=transcript or "", ocr_text=ocr_text or "")
        return low_conf

    movie_id = result["id"]
    try:
        details = await get_tv_details(movie_id, lang) \
            if search_type == "tv" else await get_movie_details(movie_id, lang)
    except Exception:
        try:
            details = await get_movie_details(movie_id, lang)
        except Exception:
            return {"status": "error", "code": "tmdb_error",
                    "message": "Impossible de récupérer les détails du film."}

    region    = {"fr": "FR", "en": "US", "es": "ES",
                 "de": "DE", "zh": "CN"}.get(lang, "FR")
    providers = (details.get("watch/providers", {})
                        .get("results", {})
                        .get(region, {})
                        .get("flatrate", []))
    is_series = search_type == "tv" or bool(details.get("first_air_date"))

    final = {
        "status":          "success",
        "media_type":      search_type,
        "is_series":       is_series,
        "title":           (result.get("meilleur_titre")
                            or details.get("title")
                            or details.get("name") or "Inconnu"),
        "confidence":      max(0, confidence),
        "synopsis":        details.get("overview", ""),
        "image":           (f"https://image.tmdb.org/t/p/w500{details['poster_path']}"
                            if details.get("poster_path") else ""),
        "streaming":       [p.get("provider_name") for p in providers],
        "streaming_logos": [{"name": p.get("provider_name"),
                             "logo_path": p.get("logo_path")}
                            for p in providers],
        "similar":         [{"title": s.get("title", s.get("name", "?")),
                             "id": s.get("id"),
                             "poster_path": s.get("poster_path")}
                            for s in details.get("similar", {})
                                           .get("results", [])[:6]],
        "cast":            [{"name": c.get("name"),
                             "character": c.get("character"),
                             "profile_path": c.get("profile_path")}
                            for c in details.get("credits", {})
                                           .get("cast", [])[:8]],
        "trailer":         "",
        "genres":          [g["name"] for g in details.get("genres", [])],
        "year":            (details.get("release_date")
                            or details.get("first_air_date") or "").split("-")[0],
        "runtime":         (details.get("runtime")
                            or (details.get("episode_run_time") or [None])[0]),
        "vote_average":    details.get("vote_average"),
        "vote_count":      details.get("vote_count"),
        "tmdb_id":         movie_id,
        "lang":            lang,
        "is_fake":         fake_score > 70,
        "seasons":         details.get("seasons") if is_series else None
    }

    if confidence >= 50:
        set_cache(url, final,
                  transcript=transcript or "",
                  ocr_text=ocr_text or "")

    return final

# ── ROUTES PUBLIQUES ──────────────────────────────────────────────
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    cache_key = f"{lang}_{type}"
    now = time.time()
    if (cache_key in _trending_cache
            and (now - _trending_cache_time.get(cache_key, 0)) < CACHE_DURATION):
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
async def discover(genre_name: str, lang: str = "fr",
                   page: int = 1, type: str = "movie"):
    GENRE_MAP = {
        "horror": 27, "horreur": 27, "action": 28, "comedy": 35, "comédie": 35,
        "science-fiction": 878, "scifi": 878, "romance": 10749, "animation": 16,
        "thriller": 53, "drama": 18, "drame": 18, "documentary": 99,
        "documentaire": 99, "fantasy": 14, "fantastique": 14,
        "crime": 80, "family": 10751, "famille": 10751,
    }
    genre_id = GENRE_MAP.get(genre_name.lower())
    if not genre_id:
        return {"status": "error",
                "message": f"Genre '{genre_name}' introuvable."}
    try:
        data = await discover_by_genre(genre_id, lang, page, media_type=type)
        return {"status": "success", **data}
    except Exception:
        return {"status": "error",
                "message": "Erreur lors du chargement du genre."}

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    try:
        return await get_tv_details(movie_id, lang) \
            if type == "tv" else await get_movie_details(movie_id, lang)
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
        merged = sorted(movies + tv,
                        key=lambda x: x.get("popularity", 0),
                        reverse=True)[:20]
        return {"status": "success", "results": merged}
    except Exception:
        return {"status": "error",
                "message": "Erreur lors de la recherche.", "results": []}

@app.get("/cache-stats")
async def get_cache_stats():
    return cache_stats()

@app.get("/sitemap.xml")
async def sitemap():
    base = "https://quelfilm.app"
    urls = [f"{base}/", f"{base}/fr", f"{base}/en",
            f"{base}/es", f"{base}/de", f"{base}/zh"]
    xml  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"  <url><loc>{u}</loc></url>\n"
    xml += "</urlset>"
    return HTMLResponse(content=xml, media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\n"
        "Sitemap: https://quelfilm.app/sitemap.xml\n")

@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")