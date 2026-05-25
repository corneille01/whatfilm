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


app = FastAPI(title="ShadowFrame AI")


# =========================
# FRONTEND
# =========================

app.mount(
    "/frontend",
    StaticFiles(directory="frontend"),
    name="frontend"
)


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


# =========================
# REQUEST MODEL
# =========================

class VideoRequest(BaseModel):
    url: str


# =========================
# ANALYSER
# =========================

@app.post("/analyser")
async def analyser(req: VideoRequest):

    # CACHE
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
                "yt-dlp",
                "-o", video_path,
                "-f", "mp4",
                "--no-playlist",
                req.url
            ],
            check=True
        )

        print("STEP 2 = EXTRACT AUDIO")

        subprocess.run(
            [
                "ffmpeg",
                "-i", video_path,
                "-y",
                audio_path
            ],
            check=True
        )

        print("STEP 3 = EXTRACT FRAMES")

        frames = extract_keyframes(
            video_path,
            frame_dir,
            max_frames=10
        )

        print("FRAMES =", frames)

        print("STEP 4 = OCR")

        ocr_text = extract_text_from_images(
        frames,
        max_images=8
        )

        print("OCR =", ocr_text)


        print("STEP 5 = TRANSCRIBE")

        transcript = transcribe(
        audio_path,
        enabled=True
        )

        print("TRANSCRIPT =", transcript)

        print("STEP 6 = GEMINI EXTRACTION")

        extraction = await multimodal_extract(
            frames,
            ocr_text,
            transcript
        )

        print("EXTRACTION =", extraction)

        print("STEP 7 = FAKE DETECTION")

        fake_score = detect_fake(
            ocr_text + transcript
        )

        print("FAKE SCORE =", fake_score)

        print("STEP 8 = SEARCH QUERY")

        query = await build_search_query(extraction)
        if not query or len(query.strip()) < 3:
            return {
                "status": "unknown",
                "message": "Impossible d'analyser la vidéo"
            }

        print("QUERY =", query)

        print("STEP 9 = TMDB SEARCH")

        candidates = await search_candidates(query)

        print("CANDIDATES =", candidates)

        if not candidates:

            return {
                "status": "unknown",
                "message": "Film introuvable"
            }

        deep_mode = should_use_deep(
            extraction,
            fake_score
        )

        print("DEEP MODE =", deep_mode)

        # =========================
        # RERANK
        # =========================

        if deep_mode:

            result = await rerank(
                extraction,
                candidates
            )

            title = result.get(
                "meilleur_titre",
                "Unknown"
            )

            confidence = result.get(
                "score",
                70
            )

        else:

            best = candidates[0]

            title = best.get(
                "title",
                best.get("name", "Unknown")
            )

            confidence = 75

        # =========================
        # POSTER
        # =========================

        best = candidates[0]

        poster = None

        if best.get("poster_path"):

            poster = (
                "https://image.tmdb.org/t/p/w500"
                + best["poster_path"]
            )

        # =========================
        # STREAMING URL
        # =========================

        media_type = best.get("media_type", "movie")

        if media_type == "tv":
            stream_url = (
                f"https://www.themoviedb.org/tv/{best['id']}"
            )

        else:
            stream_url = (
                f"https://www.themoviedb.org/movie/{best['id']}"
            )

        # =========================
        # FAKE PENALTY
        # =========================

        if fake_score > 70:
            confidence -= 15

        confidence = max(1, confidence)

        # =========================
        # FINAL RESPONSE
        # =========================

        final = {
            "status": "success",
            "title": title,
            "confidence": confidence,
            "poster": poster,
            "streaming": stream_url
        }

        set_cache(req.url, final)

        print("FINAL =", final)

        return final

    except Exception as e:

        print("ERROR =", str(e))

        return {
            "status": "error",
            "message": str(e)
        }

    finally:

        # DELETE FILES

        for f in [video_path, audio_path]:

            if os.path.exists(f):
                os.remove(f)

        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir)