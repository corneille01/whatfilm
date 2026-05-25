# vision/ocr_engine.py

import pytesseract
from PIL import Image


def extract_text_from_images(frames, max_images=8):

    texts = []

    print("OCR FRAMES =", frames)

    for frame in frames[:max_images]:

        try:

            print("READING FRAME =", frame)

            image = Image.open(frame)

            text = pytesseract.image_to_string(image)

            print("OCR TEXT =", text)

            if text.strip():
                texts.append(text.strip())

        except Exception as e:

            print("OCR ERROR =", str(e))

    final_text = " ".join(texts)

    print("FINAL OCR =", final_text)

    return final_text