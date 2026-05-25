EXTRACTION_PROMPT = """
Tu es un expert en cinéma. Analyse ces images, l'OCR et la transcription audio.

OBJECTIF : Identifier le film, la série ou le court-métrage.

RÈGLES DE SÉCURITÉ :
1. ANALYSE CRITIQUE : Si c'est une vidéo virale, amateur, pub ou hoax, indique-le dans "description_courte".
2. ACTEURS : Si tu n'es pas certain à 100% de l'identité d'un acteur, laisse la liste VIDE. Ne devine jamais.
3. PORTE DE SORTIE : Si rien ne correspond, laisse "titres_possibles" VIDE.

Réponds STRICTEMENT en format JSON :
{{
  "description_courte": "",
  "personnages": [],
  "acteurs": [],
  "titres_possibles": []
}}
"""

RERANK_PROMPT = """
Données extraites: {extraction_json}
Candidats TMDB: {candidates_json}

Ta mission :
1. Privilégie le titre sur l'acteur.
2. Si un acteur extrait ne joue PAS dans le film candidat, ignore l'acteur.
3. Si aucun film ne correspond, retourne 'inconnu'.

Return EXACTLY JSON:
{{
  "meilleur_titre": "titre exact ou 'inconnu'",
  "score": 0,
  "raison": "explication"
}}
"""