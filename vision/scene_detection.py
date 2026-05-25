import os
import subprocess


def extract_keyframes(video_path, output_dir, max_frames=10):

    os.makedirs(output_dir, exist_ok=True)

    output_pattern = os.path.join(output_dir, "frame_%03d.jpg")

    subprocess.run([
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps=1",
        "-frames:v", str(max_frames),
        output_pattern,
        "-y"
    ], check=True)

    frames = []

    for file in sorted(os.listdir(output_dir)):
        if file.endswith(".jpg"):
            frames.append(os.path.join(output_dir, file))

    return frames