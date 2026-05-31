import os
import uuid
import shutil
import subprocess
import traceback
import urllib.parse
import base64
import time
import asyncio
import sys

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ═══ IMPORTS INTERNES ═══
from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images
from vision.whisper_engine import transcribe
from core.extraction import multimodal_extract
from core.retrieval import build_cascade_queries
from data.tmdb import (
    search_candidates, get_movie_details, get_tv_details,
    get_genre_list, discover_by_genre, get_trending,
    search_tv_candidates, get_season_details,
)
from data.fake_detector import detect_fake
from core.reranker import rerank
from storage.cache import get_cache, set_cache

# ═══════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════
app = FastAPI(title="ShadowFrame")

# ═══ MIDDLEWARE RENDER : Accepter TOUS les HEAD ═══
@app.middleware("http")
async def render_head_fix(request: Request, call_next):
    if request.method == "HEAD":
        print(f"✅ HEAD {request.url.path} → 200 OK")
        return Response(status_code=200, media_type="text/html")
    return await call_next(request)

# Static files
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# ═══════════════════════════════════════════════════════════
# ROUTES DE BASE
# ═══════════════════════════════════════════════════════════
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/health")
async def health():
    return {"status": "ok"}

# ═══════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════
sessions = {}
SESSION_TIMEOUT = 300

async def cleanup_sessions():
    while True:
        now = time.time()
        expired = [sid for sid, s in sessions.items() if now - s["timestamp"] > SESSION_TIMEOUT]
        for sid in expired:
            s = sessions.pop(sid, None)
            if s:
                for path_key in ("video_path", "audio_path", "frame_dir"):
                    p = s.get(path_key)
                    if p and os.path.exists(p):
                        if os.path.isdir(p):
                            shutil.rmtree(p)
                        else:
                            os.remove(p)
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_sessions())

# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════
class VideoRequest(BaseModel):
    url: str
    lang: str = "fr"

class ContinueRequest(BaseModel):
    session_id: str
    ocr_text: str = ""
    transcript: str

# ═══════════════════════════════════════════════════════════
# ANALYSE
# ═══════════════════════════════════════════════════════════
@app.post("/analyser")
async def analyser(req: VideoRequest):
    cached = get_cache(req.url)
    if cached:
        print("✅ Cache hit")
        return {"status": "cached", **cached}

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"
    audio_exists = False
    use_local_fallback = False

    try:
        # DOWNLOAD
        print("📥 STEP 1: DOWNLOAD")
        sys.stdout.flush()
        
        dl = subprocess.run([
            "yt-dlp", "-f", "best[ext=mp4]/best", "-o", video_path,
            "--no-playlist", "--no-check-certificate", "--force-ipv4",
            "--extractor-retries", "3", "--retries", "3",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            req.url
        ], capture_output=True, text=True, timeout=60)

        if dl.returncode != 0:
            print("⚠️ yt-dlp failed, trying Playwright...")
            try:
                from vision.tiktok_downloader import get_tiktok_video_url
                import httpx
                video_url = await get_tiktok_video_url(req.url)
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(video_url)
                    with open(video_path, "wb") as f:
                        f.write(resp.content)
                print("✅ Playwright success")
            except Exception as e:
                return {"status": "error", "message": f"Download failed: {str(e)[:200]}"}

        # AUDIO
        print("🎵 STEP 2: AUDIO")
        sys.stdout.flush()
        try:
            subprocess.run(["ffmpeg", "-i", video_path, "-t", "60", "-vn", "-acodec", "mp3", "-y", audio_path],
                         check=True, capture_output=True, timeout=30)
            audio_exists = True
        except:
            pass

        # FRAMES
        print("🖼️ STEP 3: FRAMES")
        sys.stdout.flush()
        frames = extract_keyframes(video_path, frame_dir, max_frames=6)
        if not frames:
            return {"status": "error", "message": "No frames extracted"}

        # OCR
        print("🔍 STEP 4: OCR")
        sys.stdout.flush()
        ocr_text = extract_text_from_images(frames, max_images=6)

        # TRANSCRIPTION
        print("🎙️ STEP 5: TRANSCRIPTION")
        sys.stdout.flush()
        transcript = ""
        if audio_exists:
            try:
                transcript = transcribe(audio_path, enabled=True)
            except:
                use_local_fallback = True
        else:
            use_local_fallback = True

        if use_local_fallback:
            frames_b64 = []
            for fpath in frames:
                with open(fpath, "rb") as f:
                    frames_b64.append(base64.b64encode(f.read()).decode())
            audio_b64 = ""
            if audio_exists:
                with open(audio_path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode()
            
            session_id = str(uuid.uuid4())[:12]
            sessions[session_id] = {
                "url": req.url, "lang": req.lang,
                "video_path": video_path, "audio_path": audio_path,
                "frame_dir": frame_dir, "ocr_text": ocr_text,
                "timestamp": time.time()
            }
            return {
                "status": "transcription_needed",
                "session_id": session_id,
                "frames_base64": frames_b64,
                "audio_base64": audio_b64
            }

        return await process_analysis(frames, ocr_text, transcript, req.url, req.lang,
                                     video_path, audio_path, frame_dir, audio_exists)

    except Exception as e:
        print(f"❌ ERROR: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)[:400]}
    finally:
        if not use_local_fallback:
            cleanup(video_path, audio_path, frame_dir, audio_exists)

# ═══════════════════════════════════════════════════════════
# PROCESS ANALYSIS
# ═══════════════════════════════════════════════════════════
async def process_analysis(frames, ocr_text, transcript, url, lang,
                          video_path=None, audio_path=None, frame_dir=None, audio_exists=False):
    extraction = await multimodal_extract(frames, ocr_text, transcript) or {}
    fake_score = detect_fake(ocr_text + " " + transcript)
    queries = await build_cascade_queries(extraction)
    
    candidates = []
    search_type = "movie"
    
    for q in queries:
        results = await search_candidates(q, lang)
        if results:
            candidates = results; search_type = "movie"; break
    
    if not candidates:
        for q in queries:
            try:
                results = await search_tv_candidates(q, lang)
                if results:
                    candidates = results; search_type = "tv"; break
            except:
                pass
    
    if not candidates and lang != "en":
        for q in queries[:3]:
            results = await search_candidates(q, "en")
            if results:
                candidates = results; search_type = "movie"; break
        if not candidates:
            for q in queries[:3]:
                try:
                    results = await search_tv_candidates(q, "en")
                    if results:
                        candidates = results; search_type = "tv"; break
                except:
                    pass
    
    if not candidates:
        return {"status": "not_found", "message": "Film/Série introuvable"}
    
    result = await rerank(extraction, candidates)
    if not result or not result.get("id"):
        result = {"meilleur_titre": candidates[0].get("title", "Inconnu"), "id": candidates[0]["id"], "score": 35}
    
    confidence = result.get("score", 0)
    if confidence < 30:
        return {"status": "not_found", "message": "Confiance trop faible"}
    
    movie_id = result["id"]
    try:
        details = await get_tv_details(movie_id, lang) if search_type == "tv" else await get_movie_details(movie_id, lang)
    except:
        details = await get_movie_details(movie_id, lang)
    
    region = {"fr": "FR", "en": "US", "es": "ES", "de": "DE", "zh": "CN"}.get(lang, "FR")
    providers = details.get("watch/providers", {}).get("results", {}).get(region, {}).get("flatrate", [])
    is_series = search_type == "tv" or bool(details.get("first_air_date"))
    
    final = {
        "status": "success",
        "media_type": search_type,
        "is_series": is_series,
        "title": result.get("meilleur_titre") or details.get("title") or details.get("name") or "Inconnu",
        "confidence": max(0, confidence),
        "synopsis": details.get("overview", ""),
        "image": f"https://image.tmdb.org/t/p/w500{details['poster_path']}" if details.get("poster_path") else "",
        "streaming": [p.get("provider_name") for p in providers],
        "tmdb_id": movie_id,
        "year": (details.get("release_date") or details.get("first_air_date") or "").split("-")[0],
        "vote_average": details.get("vote_average"),
        "genres": [g["name"] for g in details.get("genres", [])],
    }
    
    if confidence >= 50:
        set_cache(url, final)
    
    return final

# ═══════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════
def cleanup(video_path, audio_path, frame_dir, audio_exists):
    try:
        if os.path.exists(video_path): os.remove(video_path)
        if audio_exists and os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_dir): shutil.rmtree(frame_dir)
    except:
        pass

# ═══════════════════════════════════════════════════════════
# ROUTES PUBLIQUES (version simplifiée pour l'espace)
# ═══════════════════════════════════════════════════════════
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    results = await get_trending(lang, media_type=type)
    return {"status": "success", "results": results} if results else {"status": "error", "message": "No results"}

@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1, type: str = "movie"):
    GENRE_MAP = {"horror": 27, "action": 28, "comedy": 35, "science-fiction": 878, "romance": 10749,
                 "animation": 16, "thriller": 53, "drama": 18, "documentary": 99, "fantasy": 14, "crime": 80, "family": 10751}
    genre_id = GENRE_MAP.get(genre_name.lower())
    if not genre_id:
        return {"status": "error", "message": f"Genre '{genre_name}' not found"}
    data = await discover_by_genre(genre_id, lang, page, media_type=type)
    return {"status": "success", **data}

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    return await get_tv_details(movie_id, lang) if type == "tv" else await get_movie_details(movie_id, lang)

@app.get("/rechercher")
async def rechercher(query: str, lang: str = "fr"):
    movies = await search_candidates(query, lang) or []
    try:
        tv = await search_tv_candidates(query, lang) or []
    except:
        tv = []
    return {"status": "success", "results": sorted(movies + tv, key=lambda x: x.get("popularity", 0), reverse=True)[:20]}

@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")