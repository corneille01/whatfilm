import os
import uuid
import subprocess

from worker.celery_app import celery

from vision.scene_detection import extract_keyframes
from vision.ocr_engine import extract_text_from_images
from vision.whisper_engine import transcribe
from core.extraction import multimodal_extract
from core.retrieval import search_candidates_from_extraction
from core.reranker import rerank
from data.fake_detector import detect_fake


@celery.task
def process_video(url: str):

    uid = str(uuid.uuid4())[:8]

    video_path = f"temp/{uid}.mp4"
    audio_path = f"temp/{uid}.mp3"
    frame_dir = f"temp/{uid}"

    try:
        # DOWNLOAD
        subprocess.run(["yt-dlp", "-o", video_path, url], check=True)

        # AUDIO
        subprocess.run(["ffmpeg", "-i", video_path, "-y", audio_path], check=True)

        # SCENES
        frames = extract_keyframes(video_path, frame_dir)

        # OCR
        ocr_text = extract_text_from_images(frames)

        # WHISPER
        transcript = transcribe(audio_path)

        # MULTIMODAL
        extraction = multimodal_extract(frames, ocr_text, transcript)

        # FAKE
        fake_score = detect_fake(ocr_text + transcript)

        # RETRIEVAL
        candidates = search_candidates_from_extraction(extraction)

        # RERANK
        result = rerank(extraction, candidates)

        confidence = result.get("score", 0)

        if fake_score > 70:
            confidence -= 15

        return {
            "status": "success",
            "title": result.get("meilleur_titre"),
            "confidence": confidence
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

    finally:
        for f in [video_path, audio_path]:
            if os.path.exists(f):
                os.remove(f)