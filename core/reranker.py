# core/reranker.py

import json
import os
from google import genai
from google.genai import types
from core.prompts import RERANK_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def rerank(extraction, candidates):
    if not candidates:
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "Aucun candidat"
        }

    # Simplification des résultats TMDB
    simplified = []
    for c in candidates:
        if c.get("media_type") == "person" and "known_for" in c:
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

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(simplified, ensure_ascii=False)
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        result = json.loads(response.text)

        # SÉCURITÉ : Fallback intelligent si le score est trop faible
        # Cela empêche ton frontend d'afficher "Échec de l'analyse" inutilement
        if result.get("score", 0) < 30:
            suggested = extraction.get("titres_possibles", [])
            return {
                "meilleur_titre": suggested[0] if suggested else "inconnu",
                "score": 40,
                "raison": "Score bas, fallback sur suggestion"
            }
            
        return result

    except Exception as e:
        print(f"RERANK ERROR: {e}")
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "Erreur système"
        }