"""
core/prompts.py — Prompts LLM pour l'extraction et le reranking.

Changement v2 :
  - EXTRACTION_PROMPT : les acteurs reconnus visuellement sont priorisés
    et doivent être croisés avec le transcript avant de proposer des titres.
  - RERANK_PROMPT : inchangé.
"""

EXTRACTION_PROMPT = """Tu es un expert mondial en cinéma, séries TV, anime et documentaires.
Analyse ces images extraites d'une vidéo, ce texte OCR et cette transcription audio
pour identifier l'œuvre audiovisuelle.

OCR extrait des frames :
{ocr_text}

Transcription audio (texte) :
{transcript}

ORDRE DE PRIORITÉ POUR L'IDENTIFICATION :

ÉTAPE 1 — ACTEURS (signal le plus fiable)
Regarde attentivement les visages sur les images.
Si tu reconnais formellement un acteur/actrice, note-le dans "acteurs".
Croise ensuite avec la transcription : est-ce qu'un nom, un personnage,
un lieu, ou une réplique connue correspond à l'un de ses films ?
Si oui → propose ce titre dans "titres_possibles".
Ex : tu vois Eddie Murphy + transcription parle de "Bourse" → "Un fauteuil pour deux".

ÉTAPE 2 — TITRES EXPLICITES
Titres vus dans l'OCR ou cités explicitement dans la transcription.
Si les images/transcription te rappellent fortement une œuvre connue, préfixe de "?"
Ex: ["?Les Intouchables"]. JAMAIS inventer un titre inexistant.

ÉTAPE 3 — INDICES VISUELS
Décors, costumes, logos, objets iconiques, chaînes TV (TCM, Netflix, Canal+),
véhicules, époques, lieux reconnaissables.

RÈGLES STRICTES :
1. "acteurs" : uniquement si tu reconnais FORMELLEMENT le visage OU le nom est
   cité dans la transcription. C'est le champ le plus important — sois précis.
2. "titres_possibles" : d'abord les titres issus du croisement acteur+transcript,
   puis les titres explicites OCR/audio, puis tes déductions visuelles ("?Titre").
   Si tu ne reconnais rien, laisse [].
3. "personnages" : noms de personnages visibles sur les images ou cités dans la transcription.
4. "objets_importants" : objets/logos/véhicules/lieux iconiques sur les images.
   Ex: ["DeLorean", "Hogwarts", "sabre laser"].
5. "description_courte" : décris objectivement décor, costumes, époque, action,
   ambiance ET contenu de la transcription. Très précis si tu ne reconnais pas l'œuvre.
6. "genre_apparent" : action|comédie|horreur|drame|animation|thriller|romance|documentaire|anime.
7. "annee_estimee" : année dans l'OCR/transcription ou estimable visuellement.
8. "langue_originale" : langue de la transcription (fr|en|es|de|ja|ko|zh|ar|pt).
9. "indices_visuels" : tout détail visuel utile non couvert ailleurs.
   Ex: ["uniforme scolaire japonais", "voiture années 80", "skyline New York"].

NE JAMAIS inventer. Vaut mieux un champ vide qu'une donnée fausse.
Réponds UNIQUEMENT avec ce JSON valide sur une seule ligne, sans markdown :
{{"titres_possibles":[],"acteurs":[],"personnages":[],"objets_importants":[],"description_courte":"","genre_apparent":"","annee_estimee":null,"langue_originale":"","indices_visuels":[]}}"""


RERANK_PROMPT = """Tu es un expert en identification de films et séries TV du monde entier.

Voici les indices extraits de la vidéo :
{extraction_json}

Voici les candidats trouvés sur TMDB :
{candidates_json}

RÈGLES STRICTES :
- Compare titres_possibles, acteurs, personnages, objets_importants, indices_visuels
  et description_courte avec le titre et synopsis de chaque candidat.
- Si un titre_possible correspond exactement à un candidat → score 90+.
- Si description_courte et synopsis concordent clairement → score 70+.
- Si acteurs ou personnages correspondent → bonus +10.
- Si l'année correspond → bonus +5.
- Si aucun candidat ne correspond vraiment → score < 30.
- Le score va de 0 (aucune confiance) à 100 (certitude absolue).
- "meilleur_titre" doit être le titre EXACT du champ "title" du candidat choisi.
- JAMAIS inventer un candidat qui n'est pas dans la liste.

Réponds UNIQUEMENT avec ce JSON valide sur une seule ligne, sans markdown :
{{"id":<id TMDB>,"meilleur_titre":"<titre exact>","score":<0-100>,"raison":"<explication courte>"}}"""