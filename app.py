import os
import uuid
import shutil
import subprocess
import traceback
import urllib.parse

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images
from vision.whisper_engine import transcribe

from core.extraction import multimodal_extract
from core.retrieval import build_cascade_queries
from data.tmdb import search_candidates, get_movie_details, get_tv_details, get_genre_list, discover_by_genre, get_trending, search_tv_candidates, get_season_details
from data.fake_detector import detect_fake
from core.reranker import rerank
from storage.cache import get_cache, set_cache

app = FastAPI(title="ShadowFrame")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


class VideoRequest(BaseModel):
    url: str
    lang: str = "fr"


@app.post("/analyser")
async def analyser(req: VideoRequest):
    # ── Cache ──────────────────────────────────────────────────────────
    cached = get_cache(req.url)
    if cached:
        print("STEP 0: Cache hit")
        return {"status": "cached", **cached}

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir  = f"temp/{uid}"
    audio_exists = False

    try:
        # ── 1. Download ────────────────────────────────────────────────
        print("STEP 1: DOWNLOAD VIDEO")
        dl = subprocess.run(
    [
        "yt-dlp",
        "-f", "best",
        "-o", video_path,
        "--no-playlist",
        "--cookies-from-browser", "chrome",   # si disponible
        "--extractor-args", "tiktok:app_version=26.2.1;os_version=16;device_platform=android",
        "--user-agent", "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        req.url
    ],
    capture_output=True, text=True
        )
       
        if dl.returncode != 0:
            err = dl.stderr[-400:] if dl.stderr else "unknown error"
            print(f"yt-dlp FAILED: {err}")
            return {"status": "error", "message": f"Impossible de télécharger la vidéo. ({err})"}

        # ── 2. Audio ───────────────────────────────────────────────────
        print("STEP 2: EXTRACT AUDIO")
        try:
            subprocess.run(
                ["ffmpeg", "-i", video_path, "-t", "60", "-vn",
                 "-acodec", "mp3", "-y", audio_path],
                check=True, capture_output=True
            )
            audio_exists = True
        except Exception as e:
            print(f"Audio extraction failed (silent video?): {e}")

        # ── 3. Frames ──────────────────────────────────────────────────
        print("STEP 3: EXTRACT FRAMES")
        frames = extract_keyframes(video_path, frame_dir, max_frames=6)

        # ── 4. OCR + Transcription ─────────────────────────────────────
        print("STEP 4: OCR & TRANSCRIBE")
        ocr_text   = extract_text_from_images(frames, max_images=6)
        transcript = transcribe(audio_path, enabled=True) if audio_exists else ""
        print(f"OCR length: {len(ocr_text)} | Transcript length: {len(transcript)}")

        # ── 5. Gemini extraction ───────────────────────────────────────
        print("STEP 5: GEMINI EXTRACTION")
        extraction = await multimodal_extract(frames, ocr_text, transcript)
        print(f"Extraction: {extraction}")
        if not extraction:
            extraction = {}

        # ── 6. Fake detection ──────────────────────────────────────────
        print("STEP 6: FAKE DETECTION")
        fake_score = detect_fake(ocr_text + " " + transcript)

        # ── 7. CASCADE SEARCH — movies + TV series ─────────────────────
        print("STEP 7: CASCADE TMDB SEARCH (movies + TV)")
        queries = await build_cascade_queries(extraction)
        print(f"Cascade queries: {queries}")

        candidates = []
        used_query = ""
        search_type = "movie"

        for q in queries:
            print(f"  Trying movie query: '{q}'")
            results = await search_candidates(q, req.lang)
            if results:
                candidates = results
                used_query = q
                search_type = "movie"
                print(f"  ✓ Found {len(results)} movie candidates with '{q}'")
                break
            else:
                print(f"  ✗ No movie results for '{q}'")

        # If no movie results, try TV series
        if not candidates:
            print("  → Trying TV series search...")
            for q in queries:
                print(f"  Trying TV query: '{q}'")
                try:
                    results = await search_tv_candidates(q, req.lang)
                    if results:
                        candidates = results
                        used_query = q
                        search_type = "tv"
                        print(f"  ✓ Found {len(results)} TV candidates with '{q}'")
                        break
                except Exception as e:
                    print(f"  TV search error: {e}")

        if not candidates:
            # English fallback for both movie and TV
            if req.lang != "en" and queries:
                print("  Trying fallback in English (movie)...")
                for q in queries[:3]:
                    results = await search_candidates(q, "en")
                    if results:
                        candidates = results; used_query = q; search_type = "movie"
                        print(f"  ✓ EN movie fallback: {len(results)} with '{q}'")
                        break
                if not candidates:
                    print("  Trying fallback in English (TV)...")
                    for q in queries[:3]:
                        try:
                            results = await search_tv_candidates(q, "en")
                            if results:
                                candidates = results; used_query = q; search_type = "tv"
                                print(f"  ✓ EN TV fallback: {len(results)} with '{q}'")
                                break
                        except Exception:
                            pass

        if not candidates:
            desc = extraction.get("description_courte", "")
            return {
                "status": "unknown",
                "message": (
                    f"Film/Série introuvable après {len(queries)} tentatives. "
                    f"Gemini a identifié : \"{desc[:120]}\""
                    if desc else "Introuvable. Essaie un autre lien."
                )
            }

        # ── 8. Rerank ──────────────────────────────────────────────────
        print(f"STEP 8: RERANKING {len(candidates)} candidates (query='{used_query}')")
        result = await rerank(extraction, candidates)
        print(f"Rerank result: {result}")

        if not result or not result.get("id"):
            best = candidates[0]
            result = {
                "meilleur_titre": best.get("title") or best.get("name") or "Inconnu",
                "id": best.get("id"),
                "score": 35,
            }
            print(f"Rerank fallback → {result}")

        confidence = result.get("score", 0)
        if confidence < 30:
            desc         = extraction.get("description_courte", "")
            titre_gemini = (extraction.get("titres_possibles") or [""])[0]
            query_yt     = titre_gemini or desc[:80]
            query_google = titre_gemini or desc[:100]
            print(f"Score trop bas ({confidence}) → not_found")
            return {
                "status":        "not_found",
                "message":       "Aucun film/série correspondant trouvé avec certitude.",
                "description":   desc,
                "titre_gemini":  titre_gemini,
                "search_youtube": f"https://www.youtube.com/results?search_query={urllib.parse.quote(query_yt + ' film')}",
                "search_google":  f"https://www.google.com/search?q={urllib.parse.quote(query_google + ' film')}",
                "search_tmdb":    f"https://www.themoviedb.org/search?query={urllib.parse.quote(titre_gemini or desc[:60])}",
            }

        movie_id = result.get("id")

        # ── 9. Enrichissement TMDB ─────────────────────────────────────
        print(f"STEP 9: TMDB DETAILS for id={movie_id} type={search_type}")
        details = {}
        if movie_id:
            if search_type == "tv":
                try:
                    details = await get_tv_details(movie_id, req.lang)
                except Exception:
                    details = await get_movie_details(movie_id, req.lang)
            else:
                details = await get_movie_details(movie_id, req.lang)

        # Determine region for streaming providers
        lang_region_map = {
            "fr": "FR", "en": "US", "es": "ES", "de": "DE", "zh": "CN",
        }
        region = lang_region_map.get(req.lang, "FR")

        providers_fr   = (details.get("watch/providers", {})
                          .get("results", {}).get(region, {}).get("flatrate", []))
        providers_rent = (details.get("watch/providers", {})
                          .get("results", {}).get(region, {}).get("rent", []))

        similar         = details.get("similar", {}).get("results", [])[:6]
        recommendations = details.get("recommendations", {}).get("results", [])[:6]
        cast            = details.get("credits", {}).get("cast", [])[:8]
        crew            = details.get("credits", {}).get("crew", [])
        director        = next((c for c in crew if c.get("job") == "Director"), None)
        genres          = [g["name"] for g in details.get("genres", [])]
        runtime         = details.get("runtime") or (details.get("episode_run_time") or [None])[0]
        release_date    = details.get("release_date") or details.get("first_air_date") or ""
        year            = release_date.split("-")[0] if release_date else ""
        is_series       = search_type == "tv" or bool(details.get("first_air_date"))

        trailer_data = next(
            (v for v in details.get("videos", {}).get("results", [])
             if v.get("type") == "Trailer"),
            None
        ) or next(
            (v for v in details.get("videos", {}).get("results", [])
             if v.get("type") in ["Teaser", "Clip", "Featurette"]),
            None
        )
        trailer_url = ""
        if trailer_data:
            key  = trailer_data.get("key", "")
            site = trailer_data.get("site", "")
            if site == "YouTube":
                trailer_url = f"https://www.youtube.com/watch?v={key}"

        is_fake = fake_score > 70
        if is_fake:
            confidence = max(0, confidence - 20)

        all_similar = similar + [r for r in recommendations
                                  if r.get("id") not in {s.get("id") for s in similar}]
        all_similar = all_similar[:6]

        final = {
            "status":        "success",
            "media_type":    search_type,
            "is_series":     is_series,
            "title":         (result.get("meilleur_titre")
                              or details.get("title") or details.get("name")
                              or candidates[0].get("title", "Inconnu")),
            "confidence":    max(0, confidence),
            "synopsis":      details.get("overview") or "Pas de synopsis disponible.",
            "image":         (f"https://image.tmdb.org/t/p/w500{details['poster_path']}"
                              if details.get("poster_path") else ""),
            "backdrop":      (f"https://image.tmdb.org/t/p/w1280{details['backdrop_path']}"
                              if details.get("backdrop_path") else ""),
            "streaming":     [p.get("provider_name") for p in providers_fr   if p.get("provider_name")],
            "streaming_logos": [{"name": p.get("provider_name"), "logo_path": p.get("logo_path")} for p in providers_fr],
            "streaming_rent":[p.get("provider_name") for p in providers_rent if p.get("provider_name")],
            "similar":       [{"title": s.get("title", s.get("name", "?")),
                               "id":    s.get("id"),
                               "poster_path": s.get("poster_path")} for s in all_similar],
            "cast":          [{"name":         c.get("name"),
                               "character":    c.get("character"),
                               "profile_path": c.get("profile_path")} for c in cast],
            "director":      director.get("name") if director else None,
            "is_fake":       is_fake,
            "trailer":       trailer_url,
            "genres":        genres,
            "year":          year,
            "runtime":       runtime,
            "vote_average":  details.get("vote_average"),
            "vote_count":    details.get("vote_count"),
            "tmdb_id":       movie_id,
            "search_query":  used_query,
            "scene_description": extraction.get("description_courte", ""),
        }

        if confidence >= 50:
            set_cache(req.url, final)

        return final

    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        print(f"SUBPROCESS ERROR: {err}")
        return {"status": "error", "message": f"Erreur téléchargement: {err[:200]}"}

    except Exception as e:
        print(f"UNHANDLED ERROR:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

    finally:
        if os.path.exists(video_path):                       os.remove(video_path)
        if audio_exists and os.path.exists(audio_path):     os.remove(audio_path)
        if os.path.exists(frame_dir):                        shutil.rmtree(frame_dir)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/trending")
async def trending(lang: str = "fr", type: str = "movie"):
    print(f"TRENDING: lang={lang} type={type}")
    try:
        results = await get_trending(lang, media_type=type)
        if not results:
            return {"status": "error", "message": "Impossible de charger les tendances"}
        return {"status": "success", "results": results}
    except Exception as e:
        print(f"TRENDING ERROR: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1, type: str = "movie"):
    print(f"DISCOVER: genre={genre_name}, lang={lang}, page={page}, type={type}")

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
            genre_id = next((g["id"] for g in genres
                             if g["name"].lower() == genre_name.lower()), None)
        except Exception:
            pass

    if not genre_id:
        return {"status": "error", "message": f"Genre '{genre_name}' non trouvé"}

    try:
        data = await discover_by_genre(genre_id, lang, page, media_type=type)
        return {"status": "success", "genre": genre_name, **data}
    except Exception as e:
        print(f"DISCOVER ERROR: {traceback.format_exc()}")
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
    """Retourne les détails d'une saison avec ses épisodes."""
    try:
        data = await get_season_details(series_id, season_number, lang)
        return data
    except Exception as e:
        return {"error": str(e), "episodes": []}


@app.get("/rechercher")
async def rechercher_film(query: str, lang: str = "fr"):
    try:
        # Search both movies and TV
        movie_results = await search_candidates(query, lang) or []
        tv_results = []
        try:
            tv_results = await search_tv_candidates(query, lang) or []
        except Exception:
            pass
        # Merge and sort by popularity
        all_results = movie_results + tv_results
        all_results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        return {"status": "success", "results": all_results[:20]}
    except Exception as e:
        return {"status": "error", "message": str(e), "results": []}


@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")