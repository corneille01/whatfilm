from google import genai
from config.config import GEMINI_API_KEY

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY manquante")

client = genai.Client(api_key=GEMINI_API_KEY)


async def multimodal_extract(frames, ocr_text, transcript):

    prompt = f"""
    Analyse cette vidéo TikTok et retourne uniquement un JSON valide.

    Format attendu :

    {{
      "description": "...",
      "objets": ["..."],
      "actions": ["..."],
      "genre": ["..."]
    }}

    OCR:
    {ocr_text}

    TRANSCRIPT:
    {transcript}
    """

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )

    text = response.text.strip()

    print("GEMINI =", text)

    try:
        import json
        return json.loads(text)

    except Exception:
        return {
            "description": text,
            "objets": [],
            "actions": [],
            "genre": []
        }