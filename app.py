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
        subprocess.run(
            [
                "ffmpeg", "-i", video_path, "-t", "30", "-vn",
                "-acodec", "mp3", "-y", audio_path
            ],
            check=True
        )

        print("STEP 3 = EXTRACT FRAMES")
        frames = extract_keyframes(video_path, frame_dir, max_frames=4)

        print("STEP 4 = OCR")
        ocr_text = extract_text_from_images(frames, max_images=4)
        print("OCR =", ocr_text)

        print("STEP 5 = TRANSCRIBE")
        transcript = transcribe(audio_path, enabled=True)
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

        # On force toujours la validation par l'IA
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
            if c.get("media_type") == "person" and "known_for" in c:
                for item in c["known_for"]:
                    title = item.get("title") or item.get("name")
                    if title == titre_gagnant:
                        synopsis = item.get("overview", "")
                        if item.get("poster_path"):
                            poster_url = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}"
                        break
            else:
                title = c.get("title") or c.get("name")
                if title == titre_gagnant:
                    synopsis = c.get("overview", "")
                    if c.get("poster_path"):
                        poster_url = f"https://image.tmdb.org/t/p/w500{c.get('poster_path')}"
                    break

        confidence = result.get("score", 0)
        is_fake = False
        
        if fake_score > 70:
            confidence -= 15
            is_fake = True

        final = {
            "status": "success",
            "title": titre_gagnant,
            "confidence": max(0, confidence), # Le max(0) évite les scores négatifs !
            "synopsis": synopsis,
            "image": poster_url,
            "is_fake": is_fake  # <--- On envoie l'information à la page web
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
        for f in [video_path, audio_path]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)

# --- NOUVELLES ROUTES SEO INTERNATIONALES ---
@app.get("/{lang}")
async def page_multilingue(lang: str):
    langues_supportees = ["fr", "en", "es", "de", "zh"]
    if lang in langues_supportees:
        return FileResponse("frontend/index.html")
    return FileResponse("frontend/index.html")