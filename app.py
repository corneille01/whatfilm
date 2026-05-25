import os
import uuid
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel

from scene_detection import extract_keyframes
from ocr_engine import extract_text_from_images
from whisper_engine import transcribe
from extraction import multimodal_extract
from retrieval import build_search_query
from tmdb import search_candidates
from reranker import rerank
from fake_detector import detect_fake

from storage.cache import get_cache, set_cache
from core.mode import should_use_deep
from core.early_exit import early_exit_check


app = FastAPI(title="ShadowFrame Optimized")


class VideoRequest(BaseModel):
    url: str


@app.post("/analyser")
async def analyser(req: VideoRequest):

    # =====================
    # CACHE CHECK (#1)
    # =====================
    cached = get_cache(req.url)
    if cached:
        return {
            "status": "cached",
            **cached
        }

    uid = str(uuid.uuid4())[:8]

    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"

    frames = []

    try:

        # DOWNLOAD
        subprocess.run(["yt-dlp", "-o", video_path, req.url], check=True)

        # AUDIO
        subprocess.run(["ffmpeg", "-i", video_path, "-y", audio_path], check=True)

        # SCENES (#7 optimized)
        frames = extract_keyframes(video_path, frame_dir, max_frames=10)

        # OCR (#3 optimized)
        ocr_text = extract_text_from_images(frames, max_images=8)

        # WHISPER (#2 optimized)
        transcript = transcribe(audio_path, enabled=True)

        # MULTIMODAL
        extraction = multimodal_extract(frames, ocr_text, transcript)

        # FAKE DETECTOR
        fake_score = detect_fake(ocr_text + transcript)

        # MODE DECISION (#8)
        deep_mode = should_use_deep(extraction, fake_score)

        # RETRIEVAL
        query = await build_search_query(extraction)
        candidates = await search_candidates(query)

        if not candidates:
            return {"status": "unknown", "message": "no candidates"}

        # RERANK (only if deep mode)
        if deep_mode:
            result = await rerank(extraction, candidates)
        else:
            result = {
                "meilleur_titre": candidates[0].get("title", "unknown"),
                "score": 60,
                "raison": "fast mode"
            }

        confidence = result.get("score", 0)

        # FAKE penalty
        if fake_score > 70:
            confidence -= 15

        # EARLY EXIT (#7)
        if early_exit_check(result):
            final = {
                "status": "success",
                "title": result["meilleur_titre"],
                "confidence": confidence
            }

            set_cache(req.url, final)
            return final

        final = {
            "status": "success",
            "title": result["meilleur_titre"],
            "confidence": confidence
        }

        set_cache(req.url, final)
        return final

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        for f in [video_path, audio_path]:
            if os.path.exists(f):
                os.remove(f)