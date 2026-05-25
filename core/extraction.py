import json
import os
from PIL import Image
from google import genai
from google.genai import types
from config.config import GEMINI_API_KEY

# On importe le prompt
from core.prompts import EXTRACTION_PROMPT 

client = genai.Client(api_key=GEMINI_API_KEY)

async def multimodal_extract(frames, ocr_text, transcript):
    # 1. On injecte l'OCR et le Transcript dans le prompt
    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text,
        transcript=transcript
    )

    # 2. Création du contenu multimodal (Texte + Images)
    contenu_multimodal = [prompt]
    
    for frame_path in frames:
        if os.path.exists(frame_path):
            try:
                img = Image.open(frame_path)
                contenu_multimodal.append(img)
            except Exception as e:
                print(f"Erreur lecture image {frame_path}: {e}")

    try:
        # 3. Appel à Gemini 
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contenu_multimodal,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )

        data = json.loads(response.text)
        return data

    except Exception as e:
        print("EXTRACTION ERROR =", str(e))
        return {
            "description_courte": "Erreur d'analyse",
            "personnages": [],
            "acteurs": [],
            "objets_importants": [],
            "titres_possibles": []
        }