import json
import os
from google import genai
from google.genai import types

# On importe le prompt
from core.prompts import RERANK_PROMPT 

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def rerank(extraction, candidates):
    if not candidates:
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "Aucun candidat trouvé sur TMDB"
        }

    # Simplification des résultats TMDB
   # Simplification des résultats TMDB
    simplified = []
    
    for c in candidates:
        # Si le candidat est une personne, on extrait ses films/séries les plus connus
        if c.get("media_type") == "person" and "known_for" in c:
            for item in c["known_for"]:
                simplified.append({
                    "id": item.get("id"),
                    "title": item.get("title") or item.get("name"),
                    "overview": item.get("overview", "")
                })
        else:
            # Si c'est déjà un film ou une série
            simplified.append({
                "id": c.get("id"),
                "title": c.get("title") or c.get("name"),
                "overview": c.get("overview", "")
            })

    # Injection des données (en format JSON strict) dans le prompt
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(simplified, ensure_ascii=False)
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        return json.loads(response.text)

    except Exception as e:
        print(f"RERANK ERROR: {e}")
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "Erreur lors du reranking"
        }