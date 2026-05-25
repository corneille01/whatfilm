# vision/ocr_engine.py

import pytesseract
from PIL import Image


def extract_text_from_images(frames, max_images=8):

    texts = []

    for frame in frames[:max_images]:

        try:

            image = Image.open(frame)

            text = pytesseract.image_to_string(image)

            if text.strip():
                texts.append(text.strip())

        except Exception as e:
            print("OCR ERROR =", str(e))

    return " ".join(texts)