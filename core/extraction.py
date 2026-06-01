import json
import os
import base64
import httpx
# from config.config import GEMINI_API_KEY  # gardé pour la bascule rapide

# On importe le prompt
from core.prompts import EXTRACTION_PROMPT

# ════════════════════════════════════════════════════════════════
# GEMINI — commenté, décommenter pour revenir
# ════════════════════════════════════════════════════════════════
# from google import genai
# from google.genai import types
# gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ════════════════════════════════════════════════════════════════
# GROQ — LLaVA v1.5 7B (gratuit, vision multimodale)
# https://console.groq.com → créer clé GROQ_API_KEY
# ════════════════════════════════════════════════════════════════
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_VISION_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODEL = "llava-v1.5-7b-4096-preview"  # seul modèle vision gratuit sur Groq

def _encode_image(frame_path: str) -> str | None:
    """Encode une image en base64 pour l'API Groq."""
    try:
        with open(frame_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"⚠️ Erreur encodage image {frame_path}: {e}")
        return None

async def multimodal_extract(frames, ocr_text, transcript):
    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text,
        transcript=transcript
    )

    # ── Construire le message multimodal pour Groq ──────────────
    # LLaVA sur Groq accepte max 1 image par appel (limitation API)
    # On prend la meilleure frame (la première valide)
    content = []

    # Chercher la première frame valide
    best_frame = None
    for frame_path in frames:
        if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
            best_frame = frame_path
            break

    if best_frame:
        b64 = _encode_image(best_frame)
        if b64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                }
            })

    content.append({
        "type": "text",
        "text": prompt
    })

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GROQ_VISION_URL, json=payload, headers=headers)
            response.raise_for_status()
            raw = response.json()

        text = raw["choices"][0]["message"]["content"].strip()

        # Groq ne garantit pas du JSON pur — on nettoie les fences
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        data = json.loads(text)
        return data

    except json.JSONDecodeError as e:
        print(f"⚠️ Groq JSON parse error: {e} — raw: {text[:200]}")
        # Retour minimal pour que le pipeline continue avec queries texte seul
        return {
            "description_courte": text[:300] if text else "Analyse partielle",
            "personnages": [],
            "acteurs": [],
            "objets_importants": [],
            "titres_possibles": []
        }
    except Exception as e:
        print(f"❌ EXTRACTION ERROR (Groq): {e}")
        return {
            "description_courte": "Erreur d'analyse",
            "personnages": [],
            "acteurs": [],
            "objets_importants": [],
            "titres_possibles": []
        }


# ════════════════════════════════════════════════════════════════
# BASCULE RAPIDE VERS GEMINI
# Pour revenir à Gemini :
#   1. Commenter le bloc Groq ci-dessus
#   2. Décommenter ce bloc :
# ════════════════════════════════════════════════════════════════
#
# from google import genai
# from google.genai import types
# gemini_client = genai.Client(api_key=GEMINI_API_KEY)
#
# async def multimodal_extract(frames, ocr_text, transcript):
#     prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text, transcript=transcript)
#     contenu_multimodal = [prompt]
#     for frame_path in frames:
#         if os.path.exists(frame_path):
#             try:
#                 from PIL import Image
#                 img = Image.open(frame_path)
#                 contenu_multimodal.append(img)
#             except Exception as e:
#                 print(f"Erreur lecture image {frame_path}: {e}")
#     try:
#         response = gemini_client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=contenu_multimodal,
#             config=types.GenerateContentConfig(
#                 temperature=0.2,
#                 response_mime_type="application/json"
#             )
#         )
#         return json.loads(response.text)
#     except Exception as e:
#         print("EXTRACTION ERROR =", str(e))
#         return {
#             "description_courte": "Erreur d'analyse",
#             "personnages": [], "acteurs": [],
#             "objets_importants": [], "titres_possibles": []
#         }