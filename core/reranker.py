import json, os
from google import genai
from core.prompts import RERANK_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def rerank(extraction, candidates):
    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(candidates, ensure_ascii=False)
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except:
        return {"meilleur_titre": "inconnu", "id": None, "score": 0}