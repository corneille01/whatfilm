"""
core/reranker.py — Sélection du meilleur candidat TMDB via Gemini
"""
import json
import os
import traceback

from google import genai
from core.prompts import RERANK_PROMPT

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


async def rerank(extraction: dict, candidates: list) -> dict:
    """
    Demande à Gemini de choisir le meilleur film parmi les candidats TMDB.
    Retourne toujours un dict valide avec id, meilleur_titre, score.
    """
    if not candidates:
        return {"meilleur_titre": "Inconnu", "id": None, "score": 0}

    # Fallback immédiat si un seul candidat
    if len(candidates) == 1:
        c = candidates[0]
        return {
            "meilleur_titre": c.get("title") or c.get("name") or "Inconnu",
            "id": c.get("id"),
            "score": 55,
        }

    prompt = RERANK_PROMPT.format(
        extraction_json=json.dumps(extraction, ensure_ascii=False),
        candidates_json=json.dumps(
            # On envoie seulement les champs utiles pour ne pas dépasser le contexte
            [
                {
                    "id":           c.get("id"),
                    "title":        c.get("title") or c.get("name", ""),
                    "release_date": c.get("release_date") or c.get("first_air_date", ""),
                    "overview":     (c.get("overview") or "")[:200],
                    "vote_average": c.get("vote_average"),
                    "media_type":   c.get("media_type", "movie"),
                }
                for c in candidates[:10]
            ],
            ensure_ascii=False,
        ),
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"},
        )

        raw = response.text.strip()
        print(f"RERANK RAW: {raw[:300]}")

        result = json.loads(raw)

        # Validation minimale
        if not isinstance(result, dict):
            raise ValueError(f"Rerank response n'est pas un dict : {type(result)}")

        # S'assurer que les champs obligatoires existent
        if not result.get("id"):
            raise ValueError(f"Rerank response sans id : {result}")

        # Normaliser le titre
        if not result.get("meilleur_titre"):
            matched = next((c for c in candidates if c.get("id") == result.get("id")), None)
            result["meilleur_titre"] = (
                matched.get("title") or matched.get("name") or "Inconnu"
            ) if matched else "Inconnu"

        if "score" not in result:
            result["score"] = 60

        return result

    except json.JSONDecodeError as e:
        print(f"RERANK JSON ERROR: {e} | raw={response.text[:200] if 'response' in dir() else 'N/A'}")

    except Exception as e:
        print(f"RERANK ERROR: {e}\n{traceback.format_exc()}")

    # Fallback : retourner le premier candidat avec score bas
    best = candidates[0]
    print(f"RERANK FALLBACK: utilisation du premier candidat → {best.get('title') or best.get('name')}")
    return {
        "meilleur_titre": best.get("title") or best.get("name") or "Inconnu",
        "id":    best.get("id"),
        "score": 35,
    }