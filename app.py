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
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images
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

# ═══════════════════════════════════════════════════════════
# CRÉATION DE L'APPLICATION
# ═══════════════════════════════════════════════════════════
app = FastAPI(title="ShadowFrame")

# ═══════════════════════════════════════════════════════════
# MIDDLEWARE POUR SUPPORTER LES REQUÊTES HEAD (Render)
# ═══════════════════════════════════════════════════════════
class HeadMiddleware(BaseHTTPMiddleware):
    """Convertit les requêtes HEAD en GET pour éviter les erreurs 405"""
    async def dispatch(self, request: Request, call_next):
        if request.method == "HEAD":
            # Remplacer temporairement la méthode
            request._method = "GET"
            response = await call_next(request)
            # Retourner seulement les headers sans le body
            return Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        return await call_next(request)

app.add_middleware(HeadMiddleware)

# Monter les fichiers statiques
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# ═══════════════════════════════════════════════════════════
# ROUTES DE BASE (avant tout le reste)
# ═══════════════════════════════════════════════════════════
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/health")
async def health_check():
    """Health check pour Render et load balancers"""
    return {"status": "healthy", "service": "ShadowFrame", "version": "1.0"}

# ═══════════════════════════════════════════════════════════
# SESSION STORE
# ═══════════════════════════════════════════════════════════
sessions = {}          # session_id -> { data, timestamp }
SESSION_TIMEOUT = 300  # 5 minutes

async def cleanup_sessions():
    while True:
        now = time.time()
        expired = [sid for sid, s in sessions.items() if now - s["timestamp"] > SESSION_TIMEOUT]
        for sid in expired:
            s = sessions.pop(sid, None)
            if s:
                # Nettoyer fichiers temporaires
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
# MODÈLES
# ═══════════════════════════════════════════════════════════
class VideoRequest(BaseModel):
    url: str
    lang: str = "fr"

class ContinueRequest(BaseModel):
    session_id: str
    ocr_text: str = ""
    transcript: str

# ═══════════════════════════════════════════════════════════
# ANALYSE PRINCIPALE
# ═══════════════════════════════════════════════════════════
@app.post("/analyser")
async def analyser(req: VideoRequest):
    print(f"\n{'='*60}")
    print(f"NOUVELLE ANALYSE: {req.url[:80]}")
    print(f"{'='*60}\n")
    sys.stdout.flush()
    
    # ── Cache ──────────────────────────────────────────────
    cached = get_cache(req.url)
    if cached:
        print("✅ STEP 0: Cache hit!")
        return {"status": "cached", **cached}

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir  = f"temp/{uid}"
    audio_exists = False
    use_local_fallback = False

    try:
        # ── 1. Download ────────────────────────────────────
        print("📥 STEP 1: DOWNLOAD VIDEO")
        sys.stdout.flush()
        
        dl = subprocess.run(
            [
                "yt-dlp",
                "-f", "best[ext=mp4]/best",
                "-o", video_path,
                "--no-playlist",
                "--no-check-certificate",
                "--force-ipv4",
                "--extractor-retries", "3",
                "--retries", "3",
                "--fragment-retries", "3",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--add-header", "Accept:text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "--add-header", "Accept-Language:fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "--extractor-args", "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com",
                req.url
            ],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Fallback Playwright
        if dl.returncode != 0:
            print(f"⚠️ yt-dlp échoué: {dl.stderr[:200]}")
            print("🔄 Tentative via Playwright...")
            sys.stdout.flush()
            
            try:
                from vision.tiktok_downloader import get_tiktok_video_url

                video_url = await get_tiktok_video_url(req.url)
                if not video_url:
                    raise Exception("Playwright n'a pas trouvé l'URL de la vidéo")

                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code != 200:
                        raise Exception(f"Erreur téléchargement (status {resp.status_code})")
                    with open(video_path, "wb") as f:
                        f.write(resp.content)

                print("✅ Téléchargement via Playwright réussi")
                dl = subprocess.CompletedProcess(args=[], returncode=0)

            except Exception as e:
                print(f"❌ Playwright fallback error: {e}")
                return {"status": "error", "message": f"Impossible de télécharger la vidéo. ({str(e)[:200]})"}

        # Vérification finale
        if dl.returncode != 0 or not os.path.exists(video_path):
            err = dl.stderr[-400:] if dl.stderr else "Fichier vidéo non créé"
            print(f"❌ ÉCHEC TÉLÉCHARGEMENT: {err}")
            return {"status": "error", "message": f"Impossible de télécharger la vidéo."}

        print(f"✅ Vidéo téléchargée: {os.path.getsize(video_path)} bytes")
        sys.stdout.flush()

        # ── 2. Audio ───────────────────────────────────────
        print("🎵 STEP 2: EXTRACT AUDIO")
        sys.stdout.flush()
        
        try:
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-t", "60", "-vn",
                 "-acodec", "mp3", "-y", audio_path],
                check=True, capture_output=True, timeout=30
            )
            audio_exists = True
            print(f"✅ Audio extrait: {os.path.getsize(audio_path)} bytes")
        except Exception as e:
            print(f"⚠️ Audio extraction failed (silent video?): {e}")

        # ── 3. Frames ──────────────────────────────────────
        print("🖼️ STEP 3: EXTRACT FRAMES")
        sys.stdout.flush()
        
        frames = extract_keyframes(video_path, frame_dir, max_frames=6)
        print(f"✅ {len(frames)} frames extraites")
        sys.stdout.flush()
        
        if not frames:
            print("❌ Aucune image clé extraite.")
            return {"status": "error", "message": "Impossible d'extraire les images clés."}

        # ── 4. OCR ─────────────────────────────────────────
        print("🔍 STEP 4: OCR (EasyOCR)")
        sys.stdout.flush()
        
        ocr_text = extract_text_from_images(frames, max_images=6)
        print(f"✅ OCR: {len(ocr_text)} caractères extraits")
        sys.stdout.flush()

        # ── 5. Transcription ───────────────────────────────
        print("🎙️ STEP 5: TRANSCRIPTION (Groq)")
        sys.stdout.flush()
        
        transcript = ""
        if audio_exists:
            try:
                transcript = transcribe(audio_path, enabled=True)
                print(f"✅ Transcription: {len(transcript)} caractères")
            except Exception as e:
                print(f"⚠️ Groq transcription failed: {e}")
                use_local_fallback = True
        else:
            use_local_fallback = True

        # ── Fallback local ─────────────────────────────────
        if use_local_fallback:
            print("📤 STEP 5b: Envoi au client pour transcription locale")
            sys.stdout.flush()
            
            # Préparer les frames en base64
            frames_b64 = []
            for fpath in frames:
                with open(fpath, "rb") as img_file:
                    encoded = base64.b64encode(img_file.read()).decode("utf-8")
                    frames_b64.append(encoded)

            audio_b64 = ""
            if audio_exists:
                with open(audio_path, "rb") as af:
                    audio_b64 = base64.b64encode(af.read()).decode("utf-8")

            session_id = str(uuid.uuid4())[:12]
            sessions[session_id] = {
                "url": req.url,
                "lang": req.lang,
                "video_path": video_path,
                "audio_path": audio_path,
                "frame_dir": frame_dir,
                "ocr_text": ocr_text,
                "timestamp": time.time()
            }
            return {
                "status": "transcription_needed",
                "session_id": session_id,
                "frames_base64": frames_b64,
                "audio_base64": audio_b64
            }

        # ── Suite de l'analyse ─────────────────────────────
        return await process_analysis(
            frames, ocr_text, transcript, req.url, req.lang,
            video_path, audio_path, frame_dir, audio_exists
        )

    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        print(f"❌ SUBPROCESS ERROR: {err[:200]}")
        return {"status": "error", "message": f"Erreur téléchargement: {err[:200]}"}
    except Exception as e:
        print(f"❌ UNHANDLED ERROR:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)[:400]}
    finally:
        # Nettoyer sauf si fallback local
        if not use_local_fallback:
            cleanup_files(video_path, audio_path, frame_dir, audio_exists)

# ═══════════════════════════════════════════════════════════
# FONCTION D'ANALYSE PARTAGÉE
# ═══════════════════════════════════════════════════════════
async def process_analysis(frames, ocr_text, transcript, url, lang, 
                          video_path=None, audio_path=None, frame_dir=None, audio_exists=False):
    """Traite l'analyse après l'OCR et la transcription"""
    
    # ── 6. Extraction Gemini ───────────────────────────────
    print("🤖 STEP 6: GEMINI EXTRACTION")
    sys.stdout.flush()
    
    extraction = await multimodal_extract(frames, ocr_text, transcript)
    print(f"Extraction: {str(extraction)[:200]}")
    if not extraction:
        extraction = {}

    # ── 7. Fake detection ──────────────────────────────────
    print("🔎 STEP 7: FAKE DETECTION")
    sys.stdout.flush()
    
    fake_score = detect_fake(ocr_text + " " + transcript)

    # ── 8. Cascade TMDB ────────────────────────────────────
    print("🔍 STEP 8: CASCADE TMDB SEARCH")
    sys.stdout.flush()
    
    queries = await build_cascade_queries(extraction)
    print(f"Queries: {queries}")

    candidates = []
    used_query = ""
    search_type = "movie"

    # Recherche films
    for q in queries:
        print(f"  Trying movie: '{q}'")
        results = await search_candidates(q, lang)
        if results:
            candidates = results
            used_query = q
            search_type = "movie"
            print(f"  ✅ Found {len(results)} movie candidates")
            break

    # Recherche séries
    if not candidates:
        print("  → Trying TV series...")
        for q in queries:
            try:
                results = await search_tv_candidates(q, lang)
                if results:
                    candidates = results
                    used_query = q
                    search_type = "tv"
                    print(f"  ✅ Found {len(results)} TV candidates")
                    break
            except Exception as e:
                print(f"  TV search error: {e}")

    # Fallback anglais
    if not candidates and lang != "en":
        print("  → Fallback English")
        for q in queries[:3]:
            results = await search_candidates(q, "en")
            if results:
                candidates = results; used_query = q; search_type = "movie"
                break
        if not candidates:
            for q in queries[:3]:
                try:
                    results = await search_tv_candidates(q, "en")
                    if results:
                        candidates = results; used_query = q; search_type = "tv"
                        break
                except Exception:
                    pass

    if not candidates:
        desc = extraction.get("description_courte", "")
        return {
            "status": "not_found",
            "message": f"Film/Série introuvable. {'Gemini: ' + desc[:120] if desc else 'Essayez un autre lien.'}"
        }

    # ── 9. Rerank ──────────────────────────────────────────
    print(f"📊 STEP 9: RERANKING {len(candidates)} candidates")
    sys.stdout.flush()
    
    result = await rerank(extraction, candidates)
    if not result or not result.get("id"):
        best = candidates[0]
        result = {
            "meilleur_titre": best.get("title") or best.get("name") or "Inconnu",
            "id": best.get("id"),
            "score": 35
        }

    confidence = result.get("score", 0)
    if confidence < 30:
        desc = extraction.get("description_courte", "")
        titre_gemini = (extraction.get("titres_possibles") or [""])[0]
        query_yt = titre_gemini or desc[:80]
        query_google = titre_gemini or desc[:100]
        print(f"⚠️ Score trop bas ({confidence}) → not_found")
        return {
            "status": "not_found",
            "message": "Aucun film/série correspondant trouvé avec certitude.",
            "description": desc,
            "titre_gemini": titre_gemini,
            "search_youtube": f"https://www.youtube.com/results?search_query={urllib.parse.quote(query_yt + ' film')}",
            "search_google": f"https://www.google.com/search?q={urllib.parse.quote(query_google + ' film')}",
            "search_tmdb": f"https://www.themoviedb.org/search?query={urllib.parse.quote(titre_gemini or desc[:60])}",
        }

    movie_id = result.get("id")

    # ── 10. Détails TMDB ───────────────────────────────────
    print(f"🎬 STEP 10: TMDB DETAILS id={movie_id} type={search_type}")
    sys.stdout.flush()
    
    details = {}
    if movie_id:
        try:
            if search_type == "tv":
                details = await get_tv_details(movie_id, lang)
            else:
                details = await get_movie_details(movie_id, lang)
        except Exception:
            details = await get_movie_details(movie_id, lang)

    # Construction de la réponse finale
    lang_region_map = {"fr": "FR", "en": "US", "es": "ES", "de": "DE", "zh": "CN"}
    region = lang_region_map.get(lang, "FR")

    providers_fr = details.get("watch/providers", {}).get("results", {}).get(region, {}).get("flatrate", [])
    providers_rent = details.get("watch/providers", {}).get("results", {}).get(region, {}).get("rent", [])
    similar = details.get("similar", {}).get("results", [])[:6]
    recommendations = details.get("recommendations", {}).get("results", [])[:6]
    cast = details.get("credits", {}).get("cast", [])[:8]
    crew = details.get("credits", {}).get("crew", [])
    director = next((c for c in crew if c.get("job") == "Director"), None)
    genres = [g["name"] for g in details.get("genres", [])]
    runtime = details.get("runtime") or (details.get("episode_run_time") or [None])[0]
    release_date = details.get("release_date") or details.get("first_air_date") or ""
    year = release_date.split("-")[0] if release_date else ""
    is_series = search_type == "tv" or bool(details.get("first_air_date"))

    # Trailer
    trailer_data = next(
        (v for v in details.get("videos", {}).get("results", []) if v.get("type") == "Trailer"), None
    ) or next(
        (v for v in details.get("videos", {}).get("results", []) if v.get("type") in ["Teaser", "Clip", "Featurette"]), None
    )
    trailer_url = f"https://www.youtube.com/watch?v={trailer_data['key']}" if trailer_data and trailer_data.get("site") == "YouTube" else ""

    is_fake = fake_score > 70
    if is_fake:
        confidence = max(0, confidence - 20)

    all_similar = similar + [r for r in recommendations if r.get("id") not in {s.get("id") for s in similar}]
    all_similar = all_similar[:6]

    final = {
        "status": "success",
        "media_type": search_type,
        "is_series": is_series,
        "title": (result.get("meilleur_titre") or details.get("title") or details.get("name") or "Inconnu"),
        "confidence": max(0, confidence),
        "synopsis": details.get("overview") or "Pas de synopsis disponible.",
        "image": (f"https://image.tmdb.org/t/p/w500{details['poster_path']}" if details.get("poster_path") else ""),
        "backdrop": (f"https://image.tmdb.org/t/p/w1280{details['backdrop_path']}" if details.get("backdrop_path") else ""),
        "streaming": [p.get("provider_name") for p in providers_fr if p.get("provider_name")],
        "streaming_logos": [{"name": p.get("provider_name"), "logo_path": p.get("logo_path")} for p in providers_fr],
        "streaming_rent": [p.get("provider_name") for p in providers_rent if p.get("provider_name")],
        "similar": [{"title": s.get("title", s.get("name", "?")), "id": s.get("id"), "poster_path": s.get("poster_path")} for s in all_similar],
        "cast": [{"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")} for c in cast],
        "director": director.get("name") if director else None,
        "is_fake": is_fake,
        "trailer": trailer_url,
        "genres": genres,
        "year": year,
        "runtime": runtime,
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "tmdb_id": movie_id,
        "search_query": used_query,
        "scene_description": extraction.get("description_courte", ""),
    }

    if confidence >= 50:
        set_cache(url, final)

    print(f"✅ ANALYSE TERMINÉE: {final['title']} (confiance: {confidence}%)")
    return final

# ═══════════════════════════════════════════════════════════
# NETTOYAGE DES FICHIERS
# ═══════════════════════════════════════════════════════════
def cleanup_files(video_path, audio_path, frame_dir, audio_exists):
    """Nettoie les fichiers temporaires"""
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
        if audio_exists and os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)
    except Exception as e:
        print(f"⚠️ Erreur nettoyage: {e}")

# ═══════════════════════════════════════════════════════════
# CONTINUER L'ANALYSE APRÈS TRANSCRIPTION LOCALE
# ═══════════════════════════════════════════════════════════
@app.post("/analyser_continue")
async def analyser_continue(req: ContinueRequest):
    print(f"\n📥 ANALYSE CONTINUE: session={req.session_id}")
    sys.stdout.flush()
    
    session = sessions.get(req.session_id)
    if not session:
        return {"status": "error", "message": "Session expirée ou invalide."}
    if time.time() - session["timestamp"] > SESSION_TIMEOUT:
        del sessions[req.session_id]
        return {"status": "error", "message": "Session expirée."}

    try:
        ocr_text = session.get("ocr_text") or req.ocr_text
        transcript = req.transcript
        frame_dir = session["frame_dir"]
        frames_paths = [os.path.join(frame_dir, f) for f in os.listdir(frame_dir) if f.endswith((".jpg", ".png"))]
        
        if not frames_paths:
            return {"status": "error", "message": "Aucune frame trouvée dans la session."}

        result = await process_analysis(
            frames_paths, ocr_text, transcript, 
            session["url"], session["lang"]
        )
        return result

    except Exception as e:
        print(f"❌ Error in analyser_continue: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}
    finally:
        # Nettoyer la session et les fichiers
        s = sessions.pop(req.session_id, None)
        if s:
            for path_key in ("video_path", "audio_path", "frame_dir"):
                p = s.get(path_key)
                if p and os.path.exists(p):
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)

# ═══════════════════════════════════════════════════════════
# ROUTES PUBLIQUES
# ═══════════════════════════════════════════════════════════
@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    print(f"📈 TRENDING: lang={lang} type={type}")
    try:
        results = await get_trending(lang, media_type=type)
        if not results:
            return {"status": "error", "message": "Impossible de charger les tendances"}
        return {"status": "success", "results": results}
    except Exception as e:
        print(f"❌ TRENDING ERROR: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1, type: str = "movie"):
    print(f"🎭 DISCOVER: genre={genre_name}, lang={lang}, page={page}, type={type}")
    GENRE_MAP = {
        "horror": 27, "horreur": 27, "terror": 27,
        "action": 28,
        "comedy": 35, "comédie": 35, "komödie": 35,
        "science-fiction": 878, "scifi": 878,
        "romance": 10749, "romantik": 10749,
        "animation": 16,
        "thriller": 53,
        "drama": 18, "drame": 18,
        "documentary": 99, "documentaire": 99,
        "fantasy": 14, "fantastique": 14,
        "crime": 80,
        "family": 10751, "famille": 10751,
    }
    genre_id = GENRE_MAP.get(genre_name.lower())
    if not genre_id:
        try:
            genres = await get_genre_list(lang)
            genre_id = next((g["id"] for g in genres if g["name"].lower() == genre_name.lower()), None)
        except Exception:
            pass
    if not genre_id:
        return {"status": "error", "message": f"Genre '{genre_name}' non trouvé"}
    try:
        data = await discover_by_genre(genre_id, lang, page, media_type=type)
        return {"status": "success", "genre": genre_name, **data}
    except Exception as e:
        print(f"❌ DISCOVER ERROR: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr", type: str = "movie"):
    try:
        if type == "tv":
            return await get_tv_details(movie_id, lang)
        return await get_movie_details(movie_id, lang)
    except Exception as e:
        return {"error": str(e)}

@app.get("/tv/{series_id}/season/{season_number}")
async def get_season(series_id: int, season_number: int, lang: str = "fr"):
    try:
        data = await get_season_details(series_id, season_number, lang)
        return data
    except Exception as e:
        return {"error": str(e), "episodes": []}

@app.get("/rechercher")
async def rechercher_film(query: str, lang: str = "fr"):
    try:
        movie_results = await search_candidates(query, lang) or []
        tv_results = []
        try:
            tv_results = await search_tv_candidates(query, lang) or []
        except Exception:
            pass
        all_results = movie_results + tv_results
        all_results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        return {"status": "success", "results": all_results[:20]}
    except Exception as e:
        return {"status": "error", "message": str(e), "results": []}

@app.get("/sitemap.xml")
async def sitemap():
    base = "https://quelfilm.app"
    urls = [
        f"{base}/",
        f"{base}/fr", f"{base}/en", f"{base}/es", f"{base}/de", f"{base}/zh",
        f"{base}/trending", f"{base}/trending?type=tv",
        f"{base}/discover/horror", f"{base}/discover/action",
        f"{base}/discover/comedy", f"{base}/discover/science-fiction",
        f"{base}/discover/romance", f"{base}/discover/animation",
        f"{base}/discover/thriller", f"{base}/discover/drama",
        f"{base}/discover/documentary", f"{base}/discover/fantasy",
        f"{base}/discover/crime", f"{base}/discover/family"
    ]
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in urls:
        sitemap_xml += f"  <url><loc>{url}</loc></url>\n"
    sitemap_xml += "</urlset>"
    return HTMLResponse(content=sitemap_xml, media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    content = "User-agent: *\nAllow: /\nSitemap: https://quelfilm.app/sitemap.xml\n"
    return PlainTextResponse(content)

# Route multilingue – doit être en dernier
@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")