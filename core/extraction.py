from google import genai
from google.genai import types
from PIL import Image
import json
import os

from core.prompts import EXTRACTION_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def multimodal_extract(images, ocr_text, transcript):
    contents = [
        EXTRACTION_PROMPT,
        f"OCR:\n{ocr_text}",
        f"TRANSCRIPT:\n{transcript}"
    ]

    # images safe loading
    for img in images:
        try:
            contents.append(Image.open(img))
        except Exception:
            continue

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json"
        )
    )

    try:
        return json.loads(response.text)
    except Exception:
        return {
            "personnages": [],
            "objets": [],
            "lieux": [],
            "actions": [],
            "genre": [],
            "dialogues_importants": [],
            "ambiance": [],
            "probable_fake_ai": 0
        }