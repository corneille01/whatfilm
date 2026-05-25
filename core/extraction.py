import json
import re

from google import genai
from config.config import GEMINI_API_KEY

client = genai.Client(
    api_key=GEMINI_API_KEY
)


async def multimodal_extract(
    frames,
    ocr_text,
    transcript
):

    prompt = f"""
Analyse cette vidéo TikTok et extrait :

- description courte
- objets importants
- actions importantes
- genre du film/série
- titres possibles

Réponds UNIQUEMENT en JSON.

OCR:
{ocr_text}

TRANSCRIPT:
{transcript}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    text = response.text.strip()

    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)

    try:

        data = json.loads(text)

        return data

    except Exception as e:

        print("JSON ERROR =", str(e))
        print("RAW GEMINI =", text)

        return {
            "description": text,
            "objets": [],
            "actions": [],
            "genre": [],
            "possible_titles": []
        }