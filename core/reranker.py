import json
import os
from google import genai
from google.genai import types
from core.prompts import RERANK_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def rerank(extraction, candidates):
    # Filtrage des acteurs trop obscurs
    filtered = [c for c in candidates if c.get("media_type") != "person" or c.get("popularity", 0) > 1.0]
    
    if not filtered:
        return {"meilleur_titre": "inconnu", "score": 0, "raison": "Aucun candidat pertinent"}

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(filtered, ensure_ascii=False)
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
        )
        return json.loads(response.text)
    except:
        return {"meilleur_titre": "inconnu", "score": 0, "raison": "Erreur IA"}