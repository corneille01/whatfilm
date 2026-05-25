import os
import subprocess


def extract_keyframes(video_path, output_dir, max_frames=10):

    os.makedirs(output_dir, exist_ok=True)

    output_pattern = f"{output_dir}/frame_%03d.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"fps={max_frames/10}",
            "-q:v", "2",
            output_pattern
        ],
        check=True
    )

    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".jpg")
    ])

    print("FRAMES =", frames)

    return frames[:max_frames]