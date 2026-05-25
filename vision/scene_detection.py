import cv2
import os

def extract_keyframes(video_path, output_dir, max_frames=10):

    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, total // max_frames)

    frames = []

    for i in range(max_frames):

        frame_id = i * step
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)

        ret, frame = cap.read()

        if ret:
            path = os.path.join(output_dir, f"frame_{i}.jpg")
            cv2.imwrite(path, frame)
            frames.append(path)

    cap.release()
    return frames