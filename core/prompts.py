EXTRACTION_PROMPT = """Tu es un expert mondial en cinéma, séries TV, anime et documentaires.
Analyse ces images extraites d'une vidéo, ce texte OCR et cette transcription audio
pour identifier l'œuvre audiovisuelle.

OCR extrait des frames :
{ocr_text}

Transcription audio (texte) :
{transcript}

OBJECTIF : extraire le maximum d'indices visuels ET textuels pour identifier l'œuvre.

RÈGLES STRICTES :
1. "titres_possibles" : titres vus dans l'OCR ou cités dans la transcription EXPLICITEMENT en priorité.
   Si les images ou la transcription te rappellent fortement une œuvre connue, propose-la préfixée de "?"
   Ex: ["?Les Intouchables"]. Si tu détectes une chaîne TV (TCM, Netflix, Canal+),
   utilise-le comme indice fort. JAMAIS inventer un titre inexistant.
   Si tu ne reconnais rien, laisse [].
2. "acteurs" : uniquement si tu reconnais formellement le visage sur les images OU le nom est cité explicitement dans la transcription.
3. "personnages" : noms de personnages visibles sur les images ou cités dans la transcription.
4. "objets_importants" : objets, logos, véhicules, lieux iconiques identifiables sur les images
   qui peuvent aider à identifier l'œuvre. Ex: ["DeLorean", "Hogwarts", "sabre laser"].
5. "description_courte" : décris objectivement ce que tu vois sur les images (décor, costumes,
   époque, action, ambiance) ET ce que dit la transcription. Sois très précis —
   c'est le champ le plus important si tu ne reconnais pas l'œuvre directement.
6. "genre_apparent" : action|comédie|horreur|drame|animation|thriller|romance|documentaire|anime.
7. "annee_estimee" : année mentionnée dans l'OCR/transcription, ou estimable visuellement (style, technologie, mode).
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