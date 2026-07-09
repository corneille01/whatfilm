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
- Textes à l'écran : générique, affiche, sous-titre, logo chaîne → lis-les EXACTEMENT et mets-les dans "titres_possibles" ou "ocr_visible".
- Décor, costumes, époque, style visuel → "indices_visuels".
- Objets/véhicules iconiques → "objets_importants".
- Style de production : budget apparent, qualité image, époque de tournage estimée.

IMPORTANT — TEXTE À L'ÉCRAN :
Si tu vois des caractères japonais (kanji, hiragana, katakana), coréens (hangul),
chinois, arabes ou autres scripts non-latins dans les images :
→ Lis-les et transcris-les EXACTEMENT dans "titres_possibles" avec "?" si c'est un titre probable.
→ Exemple : tu vois "千と千尋の神隠し" → mets "?千と千尋の神隠し" dans titres_possibles.
→ Ajoute aussi la romanisation si tu la connais : "?Sen to Chihiro".
→ Ces caractères sur une bannière, affiche ou générique SONT probablement le titre.

════════════════════════════════════════════════
ÉTAPE 1b — DÉTECTION CONTENU GÉNÉRÉ PAR IA
════════════════════════════════════════════════
Avant d'identifier le film, évalue si la vidéo a été générée par une IA
(Sora, Runway, Midjourney Video, Pika, Kling, Gen-2, etc.).

Signaux d'un contenu généré par IA :
- Mains avec nombre de doigts anormal (6 doigts, doigts fusionnés, manquants)
- Texte visible dans la scène flou, illisible, incohérent ou non-sens
- Mouvements de caméra irréels ou physique impossible (objets qui flottent, gravité anormale)
- Style visuel hyper-lisse, "plastique", sans grain de film, trop parfait
- Visages qui changent subtilement ou se déforment entre les frames
- Arrière-plans qui se déforment, se répètent ou ont des incohérences spatiales
- Eau, fumée, feu, cheveux avec comportement non-naturel
- Transitions de lumière irréalistes ou shadows incohérentes
- Personnages qui "glissent" plutôt que de marcher normalement
- Textures qui se répètent ou tessèlent de façon évidente

Règle : si tu détectes 2 signaux ou plus → is_ai_generated=true
        si 0 ou 1 signal seulement → is_ai_generated=false
        En cas de doute → false (mieux vaut rater un contenu IA que bloquer un vrai film)

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

IDENTIFICATION DE CONTENUS JAPONAIS/ASIATIQUES :
Si les indices visuels pointent clairement vers un contenu japonais (kimono, samouraï,
jardin japonais, temple, caractères japonais, style anime, etc.) ET qu'aucun titre
n'est encore identifié :
→ Essaie d'identifier le film/anime/drama japonais à partir de la combinaison visuelle.
→ Si tu as une piste, fournis le titre en japonais ET en romaji dans "titres_possibles"
  avec "?" (ex: ["?Rashomon", "?羅生門"]).
→ Même logique pour les contenus coréens (K-drama, film coréen), chinois, etc.

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
   - Pour les titres japonais/coréens/chinois : donne les deux formes si possible
   - JAMAIS inventer un titre inexistant
   - Si rien de certain, laisser []

   SÉRIES ANTHOLOGIQUES — RÈGLE CRITIQUE :
   Si tu identifies un épisode d'une série anthologique, mets TOUJOURS le titre
   de la SÉRIE en premier dans titres_possibles (sans "?"), puis le titre de
   l'épisode avec "?". TMDB n'indexe pas les épisodes individuellement.
   Séries anthologiques connues : Love Death + Robots, Black Mirror, Electric Dreams,
   Tales from the Loop, Amazing Stories, The Twilight Zone, Inside No. 9,
   Midnight Mass, Cabinet of Curiosities, Guillermo del Toro's Cabinet of Curiosities,
   Room 104, Creepshow.
   Exemples :
   → Tu reconnais "Automated Customer Service" (Love Death & Robots S3E1) :
     titres_possibles = ["Love, Death & Robots", "?Automated Customer Service"]
   → Tu reconnais "San Junipero" (Black Mirror S3E4) :
     titres_possibles = ["Black Mirror", "?San Junipero"]

2. "acteurs" et "acteurs_certitude" — RÈGLE ABSOLUE ANTI-HALLUCINATION :

Un acteur ne doit être listé QUE s'il est reconnu VISUELLEMENT dans les images
avec une certitude réelle ≥ 90%.

NE LISTE PAS un acteur parce que :
- tu crois avoir reconnu le film,
- le titre_possible te fait penser à ce casting,
- le synopsis correspond à un film connu,
- la vidéo ressemble à un film avec cet acteur,
- le commentaire mentionne un film dans lequel cet acteur joue,
- tu fais une déduction à partir du genre, de l'année ou du pays.

IMPORTANT :
Si tu proposes un titre avec "?", alors les acteurs associés à ce titre
NE DOIVENT PAS être listés sauf si leur visage est clairement visible dans les frames.

Pour chaque acteur listé dans "acteurs", tu DOIS fournir un score de certitude
dans "acteurs_certitude" :
- 95-100 : visage net, frontal, bien éclairé, aucun doute
- 90-94  : visage reconnaissable avec très faible doute
- <90    : NE PAS LISTER

INTERDICTIONS ABSOLUES :
- JAMAIS deviner depuis un profil de dos, flou ou partiellement visible
- JAMAIS inférer depuis un film supposé
- JAMAIS compléter le casting d'un titre_possible
- JAMAIS utiliser les acteurs connus d'un film si tu n'as pas vu leur visage
- Si doute → acteurs=[] et acteurs_certitude=[]

Si tu n'es pas certain à 90% ou plus :
acteurs=[]
acteurs_certitude=[]

Format : "Prénom Nom"
Exemple correct :
acteurs=["Brad Pitt"]
acteurs_certitude=[96]

3. "personnages" : noms de personnages vus à l'écran ou cités dans les dialogues/commentaires.

4. "objets_importants" : objets/véhicules/logos iconiques.
   Ex: ["DeLorean", "Batmobile", "sabre laser", "logo BBC", "logo Netflix"]

5. "description_courte" : 1-2 phrases MAX, ultra-concis, sur l'action principale visible.
   MAX 100 caractères. PAS de répétition.

6. "genre_apparent" : film-action|film-comédie|film-horreur|film-drame|film-thriller|film-romance|film-animation|série|série-animation|anime|documentaire|documentaire-série

7. "annee_estimee" : visible dans l'OCR/transcription, ou estimable visuellement.

8. "langue_originale" : langue principale de la transcription (fr|en|es|de|ja|ko|zh|ar|pt|it|ru)

9. "indices_visuels" : détails visuels distinctifs. MAX 5 éléments courts.

10. "is_ai_generated" : true si 2+ signaux IA détectés, false sinon.
    Signaux : doigts anormaux, texte incohérent, physique impossible, style plastique,
    visages qui se déforment, arrière-plans incohérents, mouvements non-naturels.
    En cas de doute → false.

NE JAMAIS inventer. Un champ vide vaut mieux qu'une donnée fausse.
Sois ULTRA-CONCIS sur tous les champs texte pour éviter la troncature JSON.

Réponds UNIQUEMENT avec ce JSON valide sur une seule ligne, sans markdown ni explication :
{{"titres_possibles":[],"acteurs":[],"acteurs_certitude":[],"personnages":[],"objets_importants":[],"description_courte":"","genre_apparent":"","annee_estimee":null,"langue_originale":"","indices_visuels":[],"is_ai_generated":false}}"""











RERANK_PROMPT = """Tu es un moteur strict de vérification de candidats TMDB.

Tu ne dois PAS deviner le film.
Tu dois seulement choisir le candidat TMDB le moins mauvais parmi la liste fournie.

Indices extraits de la vidéo :
{extraction_json}

Candidats TMDB :
{candidates_json}

════════════════════════════════════════
RÈGLES ABSOLUES
════════════════════════════════════════
1. Tu dois choisir UNIQUEMENT un id présent dans candidats_json.
2. Tu ne dois JAMAIS inventer un film, une série, un acteur ou une année.
3. Si les indices sont faibles, contradictoires ou basés seulement sur des acteurs incertains,
   tu dois donner un score BAS.
4. Un acteur seul ne suffit JAMAIS pour donner un score élevé.
5. Un titre_possible préfixé par "?" est une hypothèse faible, pas une preuve.
6. Si le titre_possible commence par "?", le score maximum est 80 sauf si le synopsis,
   l'année ou les objets visuels confirment fortement.
7. Si le match repose seulement sur les acteurs, le score maximum est 65.
8. Si les acteurs semblent incompatibles avec le candidat, score maximum 45.
9. Si le synopsis du candidat ne correspond pas à description_courte / indices_visuels,
   score maximum 60.
10. Si aucun candidat ne correspond vraiment, choisis le moins mauvais mais score < 35.

════════════════════════════════════════
BARÈME DE SCORE
════════════════════════════════════════
95-100 :
- Titre exact vu/cité SANS "?"
- Et synopsis/année/visuel compatibles

85-94 :
- Titre quasi exact
- Et au moins un autre indice fort confirme

70-84 :
- Titre hypothétique avec "?"
- Ou description visuelle très compatible
- Mais pas de preuve absolue

50-69 :
- Match possible mais fragile
- Acteurs ou genre seulement
- Pas assez de preuves visuelles

30-49 :
- Candidat très incertain
- Quelques éléments vagues seulement

0-29 :
- Aucun candidat ne correspond vraiment

════════════════════════════════════════
RÈGLE SPÉCIALE ACTEURS
════════════════════════════════════════
Les acteurs extraits peuvent être faux.
Ne fais pas confiance aux acteurs si :
- ils viennent d'une hypothèse de titre,
- ils ne sont pas explicitement visibles,
- ils ne sont pas confirmés par titre/synopsis/personnage.

Si le meilleur candidat est choisi principalement grâce aux acteurs,
mets un score maximum de 65.

════════════════════════════════════════
RÈGLE SPÉCIALE TITRE
════════════════════════════════════════
- titre_possible sans "?" = indice fort.
- titre_possible avec "?" = hypothèse.
- Si un titre avec "?" correspond à un candidat mais que le synopsis ne confirme pas,
  score maximum 70.

════════════════════════════════════════
SORTIE OBLIGATOIRE
════════════════════════════════════════
Réponds UNIQUEMENT avec ce JSON valide, minifié, sur UNE SEULE LIGNE.
Aucun markdown. Aucun raisonnement. Aucun texte avant ou après.

Format exact :
{{"id":123,"meilleur_titre":"Titre exact TMDB","score":65,"raison":"max 15 mots"}}
"""