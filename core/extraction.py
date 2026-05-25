import json

from google import genai
from config.config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY manquante")

client = genai.Client(api_key=GEMINI_API_KEY)


async def multimodal_extract(frames, ocr_text, transcript):

    prompt = f"""
Analyse cette vidéo TikTok et identifie le film, anime ou série.

OCR:
{ocr_text}

TRANSCRIPT:
{transcript}

Retourne STRICTEMENT un JSON valide avec ce format :

{{
  "description": "...",
  "objets": ["..."],
  "actions": ["..."],
  "genre": ["..."],
  "possible_titles": ["..."]
}}

Ne retourne AUCUN texte hors JSON.
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )

    text = response.text.strip()

    # nettoie les ```json
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(text)
        return data

    except Exception:
        return {
            "description": text,
            "objets": [],
            "actions": [],
            "genre": [],
            "possible_titles": []
        }