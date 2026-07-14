# vision/scene_detection.py
import os
import subprocess
from typing import List


def extract_keyframes(video_path: str, output_dir: str, max_frames: int = 6) -> List[str]:
    """
    Extrait max_frames images clés d'une vidéo via ffmpeg.
    Retourne uniquement les chemins de frames qui existent sur disque.
    En cas de timeout, tente d'extraire au moins 1 frame.
    En cas d'échec total, retourne [].
    """
    os.makedirs(output_dir, exist_ok=True)

    for f in os.listdir(output_dir):
        if f.endswith(('.jpg', '.png')):
            try:
                os.remove(os.path.join(output_dir, f))
            except Exception:
                pass

    def _frames_sur_disque() -> List[str]:
        result = []
        for f in sorted(os.listdir(output_dir)):
            if f.endswith(('.jpg', '.png')):
                path = os.path.join(output_dir, f)
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    result.append(path)
        return result[:max_frames]

    # ── Tentative principale : N frames à intervalles réguliers ──────────
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/{max(1, max_frames)}",
            "-frames:v", str(max_frames),
            "-q:v", "2",
            f"{output_dir}/frame_%03d.jpg",
            "-y"
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        frames = _frames_sur_disque()
        print(f"Frames extraites: {len(frames)}", flush=True)
        return frames

    except subprocess.TimeoutExpired:
        print("⏱️ Timeout extraction frames → fallback 1 frame", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ ffmpeg erreur (code {e.returncode}) → fallback 1 frame", flush=True)
    except Exception as e:
        print(f"⚠️ extract_keyframes exception: {e} → fallback 1 frame", flush=True)

    # ── Fallback : 1 frame, seek D'ENTRÉE (rapide) au lieu de seek de sortie ──
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=5
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0
        seek = max(0, duration / 2)

        cmd_fallback = [
            "ffmpeg",
            "-ss", str(seek),      # ← seek D'ENTRÉE : placé avant -i, quasi instantané
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            f"{output_dir}/frame_001.jpg",
            "-y"
        ]
        subprocess.run(cmd_fallback, check=True, capture_output=True, timeout=15)
        frames = _frames_sur_disque()
        print(f"Fallback frames: {len(frames)}", flush=True)
        return frames

    except Exception as e:
        print(f"❌ Fallback frame échoué: {e}", flush=True)

    # ── Ultime secours : frame à t=2s (évite tout risque de seek trop loin) ──
    try:
        cmd_last = [
            "ffmpeg", "-ss", "2", "-i", video_path,
            "-vframes", "1", "-q:v", "2",
            f"{output_dir}/frame_001.jpg", "-y"
        ]
        subprocess.run(cmd_last, check=True, capture_output=True, timeout=10)
        return _frames_sur_disque()
    except Exception as e:
        print(f"❌ Ultime fallback échoué: {e}", flush=True)
        return []