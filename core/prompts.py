# prompts.py

EXTRACTION_PROMPT = """
Analyse ces images tirées d'une vidéo, ainsi que le texte à l'écran (OCR) et la transcription audio.
Identifie le film ou la série. 

Concentre-toi particulièrement sur les visages pour reconnaître les acteurs, et sur l'audio pour repérer les noms des personnages.

OCR:
{ocr_text}

TRANSCRIPT:
{transcript}

Réponds STRICTEMENT avec ce format JSON (laisse les listes vides si tu ne trouves rien) :
{{
  "description_courte": "",
  "personnages": [],
  "acteurs": [],
  "objets_importants": [],
  "titres_possibles": []
}}
"""

RERANK_PROMPT = """
Tu es un vérificateur de films/séries implacable.
Voici ce que l'IA a détecté dans la vidéo :
{extraction_json}

Voici les résultats remontés par la base de données TMDB :
{candidates_json}

Ta mission : Trouver lequel des résultats TMDB correspond EXACTEMENT à la description de la vidéo. 
Si aucun ne correspond, retourne "inconnu". Le score doit être entre 0 et 100.
Tu ne doisi jamais inventer
Return EXACTLY JSON:
{{
  "meilleur_titre": "titre exact ou 'inconnu'",
  "score": 85,
  "raison": "explication courte"
}}
"""