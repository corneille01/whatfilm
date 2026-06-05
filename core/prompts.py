"""
core/prompts.py — Prompts LLM pour l'extraction et le reranking.
"""

EXTRACTION_PROMPT = """Tu es un expert mondial en cinéma, séries TV, anime et documentaires.
Tu reçois simultanément :
- Des images extraites d'une vidéo (frames)
- Un texte OCR extrait de ces images
- Une transcription (texte issu de Whisper/Groq)

OCR extrait des frames :
{ocr_text}

Transcription (texte converti par Whisper) :
{transcript}

════════════════════════════════════════════════
ÉTAPE 0 — NATURE DE LA TRANSCRIPTION
════════════════════════════════════════════════
Détermine d'abord ce que contient la transcription :
- TYPE A : dialogues du film/série (personnages qui parlent entre eux)
- TYPE B : commentaire extérieur (voix qui décrit, présente ou commente le film)
- TYPE C : mixte ou indéterminé

Si TYPE B (commentaire) : la transcription est ta source la plus riche.
  → Extrais TOUS les noms propres cités (acteurs, réalisateurs, titres, personnages).
  → Extrais TOUS les éléments narratifs décrits (lieu, action, époque, intrigue).
  → Un commentaire du type "ce film avec X qui joue Y dans Z" = titre probable.
  → IMPORTANT : si le commentaire décrit une scène précise (ex: "deux sœurs trouvent une bague dans une piscine"), c'est peut-être le synopsis d'un film connu — essaie d'identifier le film à partir de cette description narrative, même sans titre explicite. Mets-le dans "titres_possibles" avec préfixe "?".
  → Si le commentaire mentionne un genre + une année + un acteur → cherche quel film cela correspond.

Si TYPE A (dialogues) : la transcription donne l'ambiance et la langue, rarement le titre.
  → Concentre-toi sur les images pour identifier l'œuvre.
  → Cherche des répliques iconiques reconnaissables.

════════════════════════════════════════════════
ÉTAPE 1 — ANALYSE VISUELLE
════════════════════════════════════════════════
Regarde chaque image attentivement :
- Visages : si tu reconnais un acteur connu, note son nom dans "acteurs".
- Textes à l'écran : générique, affiche, sous-titre, logo chaîne → "titres_possibles" ou "objets_importants".
- Décor, costumes, époque, style visuel → "indices_visuels".
- Objets/véhicules iconiques → "objets_importants".
- Style de production : budget apparent, qualité image, époque de tournage estimée.

════════════════════════════════════════════════
ÉTAPE 2 — ANALYSE TRANSCRIPTION
════════════════════════════════════════════════
Lis la transcription en entier :
- Noms propres cités → acteurs, personnages, ou titre ?
- Lieux, dates, événements → indices temporels/géographiques.
- Répliques reconnaissables → film identifiable ?
- Si un titre est cité explicitement → "titres_possibles" sans préfixe "?".
- Si la description narrative correspond à un film que tu connais → "titres_possibles" avec "?".
- Langue de la transcription : note-la dans "langue_originale".

════════════════════════════════════════════════
ÉTAPE 3 — IDENTIFICATION PAR SYNOPSIS
════════════════════════════════════════════════
Si aucun titre n'est cité explicitement mais que la transcription décrit une scène ou intrigue :
- Essaie de reconnaître le film/la série à partir du synopsis décrit.
- Une scène de piscine + bague coincée dans une grille = film d'horreur/thriller spécifique ?
- Un groupe d'adolescents dans une école japonaise = anime ou film spécifique ?
- Deux personnages qui s'affrontent dans un décor précis = œuvre identifiable ?
- Si tu identifies quelque chose, mets-le dans "titres_possibles" avec "?" obligatoire.
- JAMAIS inventer un titre inexistant. Seulement si tu as une vraie piste.

════════════════════════════════════════════════
ÉTAPE 4 — CROISEMENT VISION + TRANSCRIPTION
════════════════════════════════════════════════
- Visage reconnu + nom cité dans la transcription → acteur confirmé dans "acteurs".
- Titre cité dans la transcription + images qui correspondent → "titres_possibles" sans "?".
- Œuvre reconnue visuellement mais non citée → "titres_possibles" avec "?" (ex: "?Inception").
- Description narrative dans la transcription + scène visible qui correspond → confirme l'œuvre.

════════════════════════════════════════════════
RÈGLES STRICTES
════════════════════════════════════════════════
1. "titres_possibles" :
   - Titre explicite (vu ou cité) → sans préfixe
   - Titre reconnu visuellement ou par synopsis → préfixé "?" (ex: "?Les Intouchables")
   - JAMAIS inventer un titre inexistant
   - Si rien de certain, laisser []

2. "acteurs" : Format "Prénom Nom". Uniquement si reconnu sur une image OU cité explicitement.

3. "personnages" : noms de personnages vus à l'écran ou cités dans les dialogues/commentaires.

4. "objets_importants" : objets/véhicules/logos iconiques.
   Ex: ["DeLorean", "Batmobile", "sabre laser", "logo Netflix", "maillot PSG"]

5. "description_courte" : synthèse en 2-4 phrases de ce que tu VOIS + ce que dit la transcription.
   Si la transcription est un commentaire descriptif, reprends-en les éléments clés ici.
   Sois TRÈS PRÉCIS sur l'action : qui fait quoi, où, avec quoi. C'est le champ de secours.
   Inclus les éléments visuels distinctifs (couleurs dominantes, décor, costumes, époque).

6. "genre_apparent" : film-action|film-comédie|film-horreur|film-drame|film-thriller|film-romance|film-animation|série|série-animation|anime|documentaire|documentaire-série

7. "annee_estimee" : visible dans l'OCR/transcription, ou estimable visuellement (style image, costumes).

8. "langue_originale" : langue principale de la transcription (fr|en|es|de|ja|ko|zh|ar|pt|it|ru)

9. "indices_visuels" : détails visuels distinctifs non couverts ailleurs.
   Ex: ["uniforme scolaire japonais", "voiture années 80", "skyline New York nuit", "piscine intérieure éclairée", "maillots de bain sombres"]

NE JAMAIS inventer. Un champ vide vaut mieux qu'une donnée fausse.

Réponds UNIQUEMENT avec ce JSON valide sur une seule ligne, sans markdown ni explication :
{{"titres_possibles":[],"acteurs":[],"personnages":[],"objets_importants":[],"description_courte":"","genre_apparent":"","annee_estimee":null,"langue_originale":"","indices_visuels":[]}}

IMPORTANT : garde description_courte sous 120 caractères. Sois ultra-concis sur tous les champs texte."""


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
- Si aucun candidat ne correspond vraiment → score < 30 mais choisis quand même le plus probable.
- Le score va de 0 (aucune confiance) à 100 (certitude absolue).
- "meilleur_titre" doit être le titre EXACT du champ "title" du candidat choisi.
- JAMAIS inventer un candidat qui n'est pas dans la liste.
- Tu DOIS toujours retourner un id valide parmi les candidats listés. JAMAIS null.

Réponds UNIQUEMENT avec ce JSON valide sur une seule ligne, sans markdown :
{{"id":<id TMDB>,"meilleur_titre":"<titre exact>","score":<0-100>,"raison":"<explication courte>"}}"""