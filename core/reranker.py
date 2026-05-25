# core/reranker.py

import json
import os
from google import genai
from google.genai import types

# Import depuis ton fichier core/prompts.py
from core.prompts import RERANK_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def rerank(extraction, candidates):
    if not candidates:
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "Aucun candidat trouvé sur TMDB"
        }

    # Simplification des résultats TMDB avec gestion des acteurs ("person")
    simplified = []
    
    for c in candidates:
        if c.get("media_type") == "person" and "known_for" in c:
            # On extrait les films/séries les plus connus de l'acteur
            for item in c["known_for"]:
                simplified.append({
                    "id": item.get("id"),
                    "title": item.get("title") or item.get("name"),
                    "overview": item.get("overview", "")
                })
        else:
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
        # On utilise le modèle Flash pour diviser le temps d'attente par 3 ou 4 !
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
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