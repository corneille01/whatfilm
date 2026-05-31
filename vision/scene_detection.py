# vision/scene_detection.py
import os
import subprocess
from typing import List

def extract_keyframes(video_path: str, output_dir: str, max_frames: int = 6) -> List[str]:
    """
    Extrait les frames clés d'une vidéo
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Supprimer les anciennes frames
    for f in os.listdir(output_dir):
        if f.endswith(('.jpg', '.png')):
            os.remove(os.path.join(output_dir, f))
    
    try:
        # Utiliser ffmpeg pour extraire des frames à intervalles réguliers
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"fps=1/{max_frames}",  # 1 frame toutes les N secondes
            "-frames:v", str(max_frames),
            "-q:v", "2",
            f"{output_dir}/frame_%03d.jpg",
            "-y"
        ]
        
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        
        # Récupérer les chemins des frames générées
        frames = []
        for f in sorted(os.listdir(output_dir)):
            if f.endswith(('.jpg', '.png')):
                frames.append(os.path.join(output_dir, f))
        
        print(f"Frames extraites: {len(frames)}")
        return frames[:max_frames]
        
    except subprocess.TimeoutExpired:
        print("Timeout lors de l'extraction des frames")
        # Fallback: extraire juste la première frame
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            f"{output_dir}/frame_001.jpg",
            "-y"
        ]
        subprocess.run(cmd, capture_output=True, timeout=10)
        return [os.path.join(output_dir, "frame_001.jpg")]
        
    except Exception as e:
        print(f"Erreur extraction frames: {e}")
        return []