import os
import subprocess


def extract_keyframes(
    video_path,
    output_dir,
    max_frames=4
):

    os.makedirs(output_dir, exist_ok=True)

    output_pattern = os.path.join(
        output_dir,
        "frame_%03d.jpg"
    )

    command = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps=0.2",
        "-frames:v", str(max_frames),
        output_pattern,
        "-y"
    ]

    subprocess.run(
        command,
        check=True
    )

    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".jpg")
    ])

    print("FRAMES =", frames)

    return frames