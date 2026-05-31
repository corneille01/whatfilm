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

from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images, start_loading
from vision.whisper_engine import transcribe

from core.extraction import multimodal_extract
from core.retrieval import build_cascade_queries
from data.tmdb import (
    search_candidates,
    get_movie_details,
    get_tv_details,
    get_genre_list,
    discover_by_genre,
    get_trending,
    search_tv_candidates,
    get_season_details,
)
from data.fake_detector import detect_fake
from core.reranker import rerank
from storage.cache import get_cache, set_cache

# ═══════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════
app = FastAPI(title="ShadowFrame")

# ── MIDDLEWARE : accepter tous les HEAD (Render) ──
@app.middleware("http")
async def render_head_fix(request: Request, call_next):
    if request.method == "HEAD":
        return Response(status_code=200)
    return await call_next(request)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# ── SESSIONS ──────────────────────────────────────
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

# ── CACHE TRENDING (5 min) ────────────────────────
_trending_cache = {}
_trending_cache_time = {}
CACHE_DURATION = 300

# ── MODELS ────────────────────────────────────────
class VideoRequest(BaseModel):
    url: str
    lang: str = "fr"

class ContinueRequest(BaseModel):
    session_id: str
    ocr_text: str = ""
    transcript: str

# ── STARTUP ───────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(cleanup_sessions())
    start_loading()
    print("✅ ShadowFrame démarré")

# ── ROUTES DE BASE ────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "ok"}

# ── UTILITAIRES ───────────────────────────────────
def cleanup_files(video_path, audio_path, frame_dir, audio_exists):
    try:
        if os.path.exists(video_path): os.remove(video_path)
        if audio_exists and os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_dir): shutil.rmtree(frame_dir)
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

# ── ANALYSE PRINCIPALE ────────────────────────────
@app.post("/analyser")
async def analyser(req: VideoRequest):
    print(f"\n📥 ANALYSE: {req.url[:80]}")
    sys.stdout.flush()
    
    cached = get_cache(req.url)
    if cached:
        return {"status": "cached", **cached}

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"
    audio_exists = False
    use_local_fallback = False

    try:
        # STEP 1: Download
        print("📥 DOWNLOAD")
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
            except Exception as e:
                return {"status": "error", "message": f"Download failed: {str(e)[:200]}"}

        # STEP 2: Audio
        print("🎵 AUDIO")
        sys.stdout.flush()
        try:
            subprocess.run(["ffmpeg", "-i", video_path, "-t", "60", "-vn", "-acodec", "mp3", "-y", audio_path],
                         check=True, capture_output=True, timeout=30)
            audio_exists = True
        except:
            pass

        # STEP 3: Frames
        print("🖼️ FRAMES")
        sys.stdout.flush()
        frames = extract_keyframes(video_path, frame_dir, max_frames=6)
        if not frames:
            return {"status": "error", "message": "No frames extracted"}

        # STEP 4: OCR
        print("🔍 OCR")
        sys.stdout.flush()
        ocr_text = extract_text_from_images(frames, max_images=6)
        if not ocr_text:
            use_local_fallback = True

        # STEP 5: Transcription
        print("🎙️ TRANSCRIPTION")
        sys.stdout.flush()
        transcript = ""
        if audio_exists:
            try:
                transcript = transcribe(audio_path, enabled=True)
            except:
                use_local_fallback = True
        else:
            use_local_fallback = True

        # Fallback client
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

        return await process_analysis(frames, ocr_text, transcript, req.url, req.lang)

    except Exception as e:
        print(f"❌ ERROR: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)[:400]}
    finally:
        if not use_local_fallback:
            cleanup_files(video_path, audio_path, frame_dir, audio_exists)

# ── ANALYSE CONTINUE ──────────────────────────────
@app.post("/analyser_continue")
async def analyser_continue(req: ContinueRequest):
    session = sessions.get(req.session_id)
    if not session:
        return {"status": "error", "message": "Session expired"}
    
    try:
        ocr_text = session.get("ocr_text") or req.ocr_text
        transcript = req.transcript
        frame_dir = session["frame_dir"]
        frames_paths = [os.path.join(frame_dir, f) for f in os.listdir(frame_dir) if f.endswith((".jpg", ".png"))]
        
        if not frames_paths:
            return {"status": "error", "message": "No frames found"}
        
        return await process_analysis(frames_paths, ocr_text, transcript, session["url"], session["lang"])
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        s = sessions.pop(req.session_id, None)
        if s:
            for path_key in ("video_path", "audio_path", "frame_dir"):
                p = s.get(path_key)
                if p and os.path.exists(p):
                    if os.path.isdir(p): shutil.rmtree(p)
                    else: os.remove(p)

# ── PROCESS ANALYSIS (shared) ─────────────────────
async def process_analysis(frames, ocr_text, transcript, url, lang):
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
            except: pass
    
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
                except: pass
    
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
        "streaming_logos": [{"name": p.get("provider_name"), "logo_path": p.get("logo_path")} for p in providers],
        "similar": [{"title": s.get("title", s.get("name", "?")), "id": s.get("id"), "poster_path": s.get("poster_path")} for s in details.get("similar", {}).get("results", [])[:6]],
        "cast": [{"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")} for c in details.get("credits", {}).get("cast", [])[:8]],
        "trailer": "",
        "genres": [g["name"] for g in details.get("genres", [])],
        "year": (details.get("release_date") or details.get("first_air_date") or "").split("-")[0],
        "runtime": details.get("runtime") or (details.get("episode_run_time") or [None])[0],
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "tmdb_id": movie_id,
        "is_fake": fake_score > 70,
        "seasons": details.get("seasons") if is_series else None
    }
    
    if confidence >= 50:
        set_cache(url, final)
    
    return final

# ── ROUTES PUBLIQUES ──────────────────────────────
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    cache_key = f"{lang}_{type}"
    now = time.time()
    
    if cache_key in _trending_cache and (now - _trending_cache_time.get(cache_key, 0)) < CACHE_DURATION:
        return _trending_cache[cache_key]
    
    try:
        results = await get_trending(lang, media_type=type)
        if not results:
            return {"status": "error", "message": "No results"}
        response = {"status": "success", "results": results}
        _trending_cache[cache_key] = response
        _trending_cache_time[cache_key] = now
        return response
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1, type: str = "movie"):
    GENRE_MAP = {
        "horror": 27, "horreur": 27, "action": 28, "comedy": 35, "comédie": 35,
        "science-fiction": 878, "scifi": 878, "romance": 10749, "animation": 16,
        "thriller": 53, "drama": 18, "drame": 18, "documentary": 99, "documentaire": 99,
        "fantasy": 14, "fantastique": 14, "crime": 80, "family": 10751, "famille": 10751,
    }
    genre_id = GENRE_MAP.get(genre_name.lower())
    if not genre_id:
        return {"status": "error", "message": f"Genre '{genre_name}' not found"}
    data = await discover_by_genre(genre_id, lang, page, media_type=type)
    return {"status": "success", **data}

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    return await get_tv_details(movie_id, lang) if type == "tv" else await get_movie_details(movie_id, lang)

@app.get("/tv/{series_id}/season/{season_number}")
async def get_season(series_id: int, season_number: int, lang: str = "fr"):
    return await get_season_details(series_id, season_number, lang)

@app.get("/rechercher")
async def rechercher(query: str, lang: str = "fr"):
    movies = await search_candidates(query, lang) or []
    try:
        tv = await search_tv_candidates(query, lang) or []
    except:
        tv = []
    return {"status": "success", "results": sorted(movies + tv, key=lambda x: x.get("popularity", 0), reverse=True)[:20]}

@app.get("/sitemap.xml")
async def sitemap():
    base = "https://quelfilm.app"
    urls = [f"{base}/", f"{base}/fr", f"{base}/en", f"{base}/es", f"{base}/de", f"{base}/zh"]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in urls:
        xml += f"  <url><loc>{url}</loc></url>\n"
    xml += "</urlset>"
    return HTMLResponse(content=xml, media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    return PlainTextResponse("User-agent: *\nAllow: /\nSitemap: https://quelfilm.app/sitemap.xml\n")

@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")