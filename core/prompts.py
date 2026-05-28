"""
core/prompts.py — Prompts Gemini pour extraction et reranking
"""

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION MULTIMODALE
# Règle d'or : Gemini ne doit JAMAIS inventer un titre.
# Si incertain → titres_possibles doit être [] ou contenir UNIQUEMENT des titres
# qu'il reconnaît vraiment comme des œuvres existantes.
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """Tu es un expert en cinéma et séries TV. Analyse ces frames vidéo, ce texte OCR et cette transcription audio pour identifier l'œuvre (film, série, anime, documentaire).

OCR extrait des frames :
{ocr_text}

Transcription audio :
{transcript}

RÈGLES ABSOLUES :
1. "titres_possibles" ne doit contenir QUE des titres d'œuvres réellement existantes que tu reconnais avec certitude. Si tu n'es pas sûr à 70% qu'une œuvre avec ce titre exact existe vraiment, laisse la liste VIDE.
2. NE JAMAIS inventer ou déduire un titre. "Clanton's Revenge" ou "Clanton County" ne sont PAS des titres de films connus — ne les mets pas dans titres_possibles.
3. Pour les acteurs et personnages : mets uniquement ce que tu reconnais visuellement ou entends clairement.
4. description_courte : décris ce que tu vois objectivement (lieu, action, ambiance, genre apparent).
5. Si tu identifies un acteur connu, son nom SEUL dans "acteurs" peut suffire pour trouver le film.

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


# ─────────────────────────────────────────────────────────────────────────────
# RERANKING
# ─────────────────────────────────────────────────────────────────────────────

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