EXTRACTION_PROMPT = """Tu es un expert en cinéma et séries TV. Analyse ce texte OCR et cette transcription audio pour identifier l'œuvre (film, série, anime, documentaire).

OCR extrait des frames :
{ocr_text}

Transcription audio :
{transcript}

OBJECTIF : extraire le maximum d'indices pour identifier l'œuvre. Le reranker validera ensuite.

RÈGLES :
1. "titres_possibles" : mets les titres que tu entends ou lis EXPLICITEMENT 
   dans le texte. Si tu n'en entends aucun mais que la scène te rappelle 
   une œuvre connue, propose-la préfixée de "?" (ex: "?Les Intouchables").
   Si tu détectes une chaîne TV ou plateforme (ex: TCM, Netflix, Canal+), 
   c'est un indice fort — utilise-le pour deviner le film diffusé si possible.
2. "acteurs" : noms entendus clairement ou visibles dans le texte.
3. "personnages" : noms de personnages cités (souvent == titre pour séries/anime).
4. "description_courte" : décris objectivement le contenu (lieu, action, genre, ambiance, langue parlée). Sois précis — c'est le fallback si les titres échouent.
5. "genre_apparent" : action, comédie, horreur, drame, animation, documentaire…
6. "annee_estimee" : si une année est mentionnée ou visible.
7. "langue_originale" : langue parlée dans la vidéo.


Réponds UNIQUEMENT avec ce JSON (pas de markdown, pas d'explication) :
{{
  "titres_possibles": [],
  "acteurs": [],
  "personnages": [],
  "description_courte": "",
  "genre_apparent": "",
  "annee_estimee": null,
  "langue_originale": ""
}}"""


RERANK_PROMPT = """Tu es un expert en identification de films et séries.

Voici ce que l'IA a extrait de la vidéo :
{extraction_json}

Voici les candidats trouvés sur TMDB :
{candidates_json}

Choisis le candidat qui correspond le mieux à l'extraction. 

RÈGLES :
- Si aucun candidat ne correspond vraiment, choisis quand même le plus probable et mets score < 30.
- Le score va de 0 (aucune confiance) à 100 (certitude absolue).
- "meilleur_titre" doit être le titre EXACT du candidat choisi (champ "title").

Réponds UNIQUEMENT avec ce JSON (pas de markdown) :
{{
  "id": <id TMDB du meilleur candidat>,
  "meilleur_titre": "<titre exact>",
  "score": <0-100>,
  "raison": "<explication courte>"
}}"""