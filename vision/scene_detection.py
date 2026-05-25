import os
from scenedetect import detect, ContentDetector
import cv2


def extract_keyframes(video_path, output_dir, max_frames=10):

    os.makedirs(output_dir, exist_ok=True)

    scenes = detect(
        video_path,
        ContentDetector(threshold=27.0)
    )

    cap = cv2.VideoCapture(video_path)

    frames = []

    for i, scene in enumerate(scenes[:max_frames]):

        start_time = scene[0]

        frame_number = start_time.get_frames()

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        success, frame = cap.read()

        if success:

            frame_path = os.path.join(
                output_dir,
                f"frame_{i}.jpg"
            )

            cv2.imwrite(frame_path, frame)

            frames.append(frame_path)

    cap.release()

    return frames