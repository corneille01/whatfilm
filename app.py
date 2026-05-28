import os
import uuid
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images
from vision.whisper_engine import transcribe

from core.extraction import multimodal_extract
from core.retrieval import build_search_query
from data.tmdb import search_candidates, get_movie_details, get_genre_list, discover_by_genre, get_trending
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
    lang: str = "en" 

@app.post("/analyser")
async def analyser(req: VideoRequest):
    # 1. Vérification du cache
    cached = get_cache(req.url)
    if cached:
        print("STEP 0: Cache trouvé")
        return {"status": "cached", **cached}

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)
    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"
    audio_exists = False

    try:
        print("STEP 1: DOWNLOAD VIDEO")
        subprocess.run(["yt-dlp", "-f", "mp4", "-o", video_path, "--no-playlist", req.url], check=True)
        
        print("STEP 2: EXTRACT AUDIO")
        try:
            subprocess.run(["ffmpeg", "-i", video_path, "-t", "30", "-vn", "-acodec", "mp3", "-y", audio_path], 
                           check=True, capture_output=True)
            audio_exists = True
        except:
            print("VIDÉO MUETTE")

        print("STEP 3: EXTRACT FRAMES")
        frames = extract_keyframes(video_path, frame_dir, max_frames=4)

        print("STEP 4: OCR & TRANSCRIBE")
        ocr_text = extract_text_from_images(frames, max_images=4)
        transcript = transcribe(audio_path, enabled=True) if audio_exists else ""
        
        print("STEP 5: GEMINI EXTRACTION")
        extraction = await multimodal_extract(frames, ocr_text, transcript)
        
        print("STEP 6: FAKE DETECTION")
        fake_score = detect_fake(ocr_text + transcript)
        
        print("STEP 7: TMDB SEARCH & RERANKING")
        query = await build_search_query(extraction)
        candidates = await search_candidates(query, req.lang)
        if not candidates:
            return {"status": "unknown", "message": "Film introuvable"}
        
        result = await rerank(extraction, candidates)
        movie_id = result.get("id")
        
        # Enrichissement dynamique (Streaming, Trailers, Similaires)
        details = await get_movie_details(movie_id, req.lang) if movie_id else {}
        providers = details.get("watch/providers", {}).get("results", {}).get("FR", {}).get("flatrate", [])
        similar = details.get("similar", {}).get("results", [])[:3]
        
        confidence = result.get("score", 0)
        is_fake = fake_score > 70
        if is_fake: confidence = max(0, confidence - 20)
        
       # Extraction dynamique et robuste du trailer
        trailer_data = next((v for v in details.get("videos", {}).get("results", []) if v["type"] == "Trailer"), None)
        trailer_url = ""
        
        if trailer_data:
            site = trailer_data.get("site")
            key = trailer_data.get("key")
            
            # Dictionnaire dynamique des modèles d'URL
            templates = {
                "YouTube": f"https://www.youtube.com/watch?v={key}",
                "Vimeo": f"https://vimeo.com/{key}",
                "Facebook": f"https://www.facebook.com/video.php?v={key}"
            }
            
            # Utilise le modèle si trouvé, sinon fallback générique
            trailer_url = templates.get(site, f"https://www.google.com/search?q={result.get('meilleur_titre')}+trailer")

        final = {
            "status": "success",
            "title": result.get("meilleur_titre", "Inconnu"),
            "confidence": max(0, confidence),
            "synopsis": details.get("overview", "Pas de synopsis disponible."),
            "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}",
            "streaming": [p["provider_name"] for p in providers],
            "similar": [{"title": s["title"], "id": s["id"]} for s in similar],
            "is_fake": is_fake,
            "trailer": trailer_url,
            "cast": [{"name": c["name"]} for c in details.get("credits", {}).get("cast", [])[:5]]
        }
        
        if confidence >= 60:
            set_cache(req.url, final)
            
        return final

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}

    finally:
        if os.path.exists(video_path): os.remove(video_path)
        if audio_exists and os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_dir): shutil.rmtree(frame_dir)

@app.get("/trending")
async def trending(lang: str = "fr"):
    print("STEP SEO: Récupération Tendances")
    return {"status": "success", "results": await get_trending(lang)}

@app.get("/discover/{genre_name}")
async def discover(genre_name: str, lang: str = "fr", page: int = 1):
    print(f"STEP SEO: Découverte genre {genre_name}")
    
    # Mapping universel des ID de genres TMDB (indépendant de la langue)
    GENRE_MAP = {
        "horror": 27, "horreur": 27, "terror": 27,
        "action": 28,
        "comedy": 35, "comédie": 35,
        "science-fiction": 878, "scifi": 878, "科幻": 878
    }
    
    # On récupère l'ID via notre mapping interne plutôt que de demander à TMDB à chaque fois
    genre_id = GENRE_MAP.get(genre_name.lower())
    data = await discover_by_genre(genre_id, lang, page)
    return {"status": "success", "genre": genre_name, **data}
    
    if not genre_id:
        # Fallback : si pas dans le mapping, on essaie quand même la méthode dynamique
        genres = await get_genre_list(lang)
        genre_id = next((g["id"] for g in genres if g["name"].lower() == genre_name.lower()), None)
    
    if not genre_id:
        return {"status": "error", "message": "Genre non trouvé"}
    
    movies = await discover_by_genre(genre_id, lang)
    return {"status": "success", "genre": genre_name, "results": movies}



@app.get("/movie/{movie_id}")
async def get_movie(movie_id: int, lang: str = "fr"):
    # get_movie_details est déjà dans ton tmdb.py
    details = await get_movie_details(movie_id, lang)
    return details

@app.get("/rechercher")
async def rechercher_film(query: str, lang: str = "fr"):
    # On utilise ta fonction search_candidates de tmdb.py
    results = await search_candidates(query, lang)
    return {"status": "success", "results": results}

@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")