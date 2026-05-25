# core/reranker.py

from google import genai
from google.genai import types
import json
import os

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


async def rerank(extraction, candidates):

    if not candidates:
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "no candidates"
        }

    simplified = [
        {
            "id": c.get("id"),
            "title": c.get("title") or c.get("name"),
            "overview": c.get("overview", ""),
        }
        for c in candidates
    ]

    prompt = f"""
Compare strictement.

{json.dumps(extraction, ensure_ascii=False)}
{json.dumps(simplified, ensure_ascii=False)}

Return JSON:
{{
  "meilleur_titre": "",
  "score": 0,
  "raison": ""
}}
"""

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

    except:
        return {
            "meilleur_titre": "inconnu",
            "score": 0,
            "raison": "error"
        }