"""
core/prompts.py — Prompts Gemini pour extraction et reranking
"""

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION MULTIMODALE
# Règle d'or : Gemini ne doit JAMAIS inventer un titre.
# Si incertain → titres_possibles doit être [] ou contenir UNIQUEMENT des titres
# qu'il reconnaît vraiment comme des œuvres existantes.
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """Tu es un expert en cinéma et séries TV. Analyse ce texte OCR et cette transcription audio pour identifier l'œuvre (film, série, anime, documentaire).

OCR extrait des frames :
{ocr_text}

Transcription audio :
{transcript}

OBJECTIF : extraire le maximum d'indices pour identifier l'œuvre. Le reranker validera ensuite.

RÈGLES :
1. "titres_possibles" : mets les titres que tu entends ou lis EXPLICITEMENT 
   dans le texte. Si tu n'en entends aucun, laisse vide — n'invente pas. 
   La description_courte servira de fallback.
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