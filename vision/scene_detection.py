import cv2
import os
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector


def extract_keyframes(video_path, output_dir, max_frames=10):
    os.makedirs(output_dir, exist_ok=True)

    video_manager = VideoManager([video_path])
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=30))

    video_manager.start()
    scene_manager.detect_scenes(frame_source=video_manager)

    scenes = scene_manager.get_scene_list()

    cap = cv2.VideoCapture(video_path)

    frames = []

    for i, scene in enumerate(scenes[:max_frames]):
        frame_number = scene[0].get_frames()

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()

        if ret:
            frame_path = os.path.join(output_dir, f"scene_{i}.jpg")
            cv2.imwrite(frame_path, frame)
            frames.append(frame_path)

    cap.release()

    return frames