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

from data.tmdb import search_candidates
from data.fake_detector import detect_fake

from core.reranker import rerank
from storage.cache import get_cache, set_cache

from core.mode import should_use_deep

app = FastAPI(title="ShadowFrame")

app.mount(
    "/frontend",
    StaticFiles(directory="frontend"),
    name="frontend"
)

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

# La requête attend l'URL et la langue (par défaut "en")
class VideoRequest(BaseModel):
    url: str
    lang: str = "en" 

@app.post("/analyser")
async def analyser(req: VideoRequest):
    cached = get_cache(req.url)
    if cached:
        return {
            "status": "cached",
            **cached
        }

    uid = str(uuid.uuid4())[:8]
    os.makedirs("temp", exist_ok=True)

    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"

    try:
        print("STEP 1 = DOWNLOAD VIDEO")
        subprocess.run(
            [
                "yt-dlp", "-f", "mp4", "-o", video_path,
                "--no-playlist", req.url
            ],
            check=True
        )

        print("STEP 2 = EXTRACT AUDIO (MAX 30 SEC)")
        audio_exists = False
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", video_path, "-t", "30", "-vn",
                    "-acodec", "mp3", "-y", audio_path
                ],
                check=True, capture_output=True
            )
            audio_exists = True
        except subprocess.CalledProcessError:
            print("VIDÉO MUETTE - Passage en mode muet")

        print("STEP 3 = EXTRACT FRAMES")
        frames = extract_keyframes(video_path, frame_dir, max_frames=4)

        print("STEP 4 = OCR")
        ocr_text = extract_text_from_images(frames, max_images=4)
        print("OCR =", ocr_text)

        print("STEP 5 = TRANSCRIBE")
        transcript = transcribe(audio_path, enabled=True) if audio_exists else "Aucun audio détecté."
        print("TRANSCRIPT =", transcript)

        print("STEP 6 = GEMINI EXTRACTION")
        extraction = await multimodal_extract(frames, ocr_text, transcript)
        print("EXTRACTION =", extraction)

        print("STEP 7 = FAKE DETECTION")
        fake_score = detect_fake(ocr_text + transcript)
        print("FAKE SCORE =", fake_score)

        print("STEP 8 = SEARCH QUERY")
        query = await build_search_query(extraction)
        print("QUERY =", query)

        print(f"STEP 9 = TMDB SEARCH (Langue: {req.lang})")
        candidates = await search_candidates(query, req.lang)
        print("CANDIDATES =", candidates)

        if not candidates:
            return {
                "status": "unknown",
                "message": "Film introuvable"
            }

        deep_mode = True
        print("DEEP MODE =", deep_mode)

        if deep_mode:
            result = await rerank(extraction, candidates)
        else:
            best = candidates[0]
            result = {
                "meilleur_titre": best.get("title", best.get("name", "unknown")),
                "score": 75,
                "raison": "fast mode"
            }

        titre_gagnant = result.get("meilleur_titre", "inconnu")
        synopsis = ""
        poster_url = ""

        # Récupération de l'image et du synopsis via les candidats TMDB
        for c in candidates:
            items = c.get("known_for", []) if c.get("media_type") == "person" else [c]
            for item in items:
                title = item.get("title") or item.get("name")
                if title and title.lower() == titre_gagnant.lower():
                    synopsis = item.get("overview", "")
                    if item.get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}"
                    break
            if poster_url: break

        confidence = result.get("score", 0)
        is_fake = False
        
        if fake_score > 70:
            confidence -= 15
            is_fake = True

        final = {
            "status": "success",
            "title": titre_gagnant,
            "confidence": max(0, confidence),
            "synopsis": synopsis,
            "image": poster_url,
            "is_fake": is_fake
        }

        set_cache(req.url, final)
        return final

    except Exception as e:
        print("ERROR =", str(e))
        return {
            "status": "error",
            "message": str(e)
        }

    finally:
        if os.path.exists(video_path): os.remove(video_path)
        if audio_exists and os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_dir): shutil.rmtree(frame_dir)

# --- ROUTES SEO INTERNATIONALES ---
@app.get("/{lang}")
async def page_multilingue(lang: str):
    return FileResponse("frontend/index.html")