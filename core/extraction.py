# core/extraction.py

import json
from google import genai
from config.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)


async def multimodal_extract(frames, ocr_text, transcript):

    prompt = f"""
Analyse cette vidéo TikTok.

OCR:
{ocr_text}

TRANSCRIPT:
{transcript}

Retourne STRICTEMENT un JSON valide :

{{
  "description": "...",
  "objets": [],
  "actions": [],
  "genre": [],
  "possible_titles": []
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")

    try:
        return json.loads(text)

    except Exception:
        return {
            "description": text,
            "objets": [],
            "actions": [],
            "genre": [],
            "possible_titles": []
        }