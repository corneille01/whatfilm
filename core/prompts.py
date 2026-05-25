# core/prompts.py

EXTRACTION_PROMPT = """
Analyse ces images tirées d'une vidéo, ainsi que le texte à l'écran (OCR) et la transcription audio.
Identifie le film ou la série. 

Concentre-toi sur les visages et l'audio. 
IMPORTANT : Si tu n'es pas certain à 100% de l'identité d'un acteur, NE L'INVENTE PAS, laisse la liste vide. 
Si le contenu semble être une vidéo truquée, un "fake" ou un montage amateur, indique-le dans la description.

OCR:
{ocr_text}

TRANSCRIPT:
{transcript}

Réponds STRICTEMENT avec ce format JSON :
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
Voici les données extraites de la vidéo :
{extraction_json}

Voici les résultats potentiels de la base de données TMDB :
{candidates_json}

Ta mission :
1. Compare la description de la vidéo avec les résumés TMDB.
2. Si un candidat correspond, donne-lui un score élevé (80-100).
3. Si les acteurs détectés dans la vidéo ne jouent PAS dans les films trouvés, le score doit être très bas (<30).
4. Si tu as un doute, sois prudent. Si aucun film ne correspond, retourne "inconnu".
5. NE JAMAIS inventer de titre qui n'est pas dans la liste fournie.

Return EXACTLY JSON:
{{
  "meilleur_titre": "titre exact ou 'inconnu'",
  "score": 0,
  "raison": "explication courte"
}}
"""