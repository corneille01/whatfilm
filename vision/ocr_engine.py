import pytesseract
from PIL import Image


def extract_text_from_images(images, max_images=8):

    texts = []

    for img_path in images[:max_images]:

        try:
            image = Image.open(img_path)

            text = pytesseract.image_to_string(image)

            if text.strip():
                texts.append(text)

        except Exception as e:
            print("OCR error:", e)

    return "\n".join(texts)