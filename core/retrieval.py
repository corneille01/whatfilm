"""
core/retrieval.py — Construction des requêtes de recherche TMDB.

Ordre de priorité v2 :
  1. Acteurs reconnus × mots-clés transcript  (signal le plus fiable)
  2. Titres certains extraits
  3. Titres + acteur combinés
  4. Acteur + genre + année
  5. Personnages iconiques
  6. Objets / indices visuels
  7. Titres incertains ("?Titre")
  8. Description libre (dernier recours)
"""

import re
from data.tmdb import search_person, get_person_credits


# ════════════════════════════════════════════════════════════════
# MOTS-CLÉS TRANSCRIPT → requête croisée acteur
# Extrait les mots significatifs du transcript pour former
# une requête "acteur + contexte" plus précise que "acteur seul".
# ════════════════════════════════════════════════════════════════
def _keywords_from_transcript(transcript: str, n: int = 3) -> list[str]:
    """
    Extrait les N mots les plus significatifs du transcript.
    Ignore les stopwords et les mots trop courts.
    Retourne [] si transcript vide.
    Ex: "les frères Duke ont décidé de vendre la bourse"
        → ["frères", "Duke", "bourse"]
    """
    if not transcript:
        return []
    # Majuscules = noms propres → priorité
    proper_nouns = re.findall(r"\b[A-ZÀ-Ÿ][a-zà-ÿ]{2,}\b", transcript)
    # Mots longs en minuscules
    long_words = [
        w for w in re.findall(r"\b[a-zà-ÿ]{5,}\b", transcript.lower())
        if w not in _STOPWORDS
    ]
    combined = list(dict.fromkeys(proper_nouns + long_words))
    return combined[:n]


# ════════════════════════════════════════════════════════════════
# BUILD CASCADE QUERIES
# ════════════════════════════════════════════════════════════════
async def build_cascade_queries(extraction: dict) -> list[str]:
    """
    Génère une liste ordonnée de requêtes TMDB.
    Priorité : acteurs×transcript → titres → acteur seul → indices.
    """
    queries = []

    titres           = [str(t) for t in extraction.get("titres_possibles", [])
                        if t and not str(t).startswith("?")]
    titres_uncertain = [str(t)[1:] for t in extraction.get("titres_possibles", [])
                        if str(t).startswith("?")]
    acteurs          = [str(a) for a in (extraction.get("acteurs", []) or []) if a]
    personnages      = [str(p) for p in (extraction.get("personnages", []) or []) if p]
    genre            = str(extraction.get("genre_apparent", "") or "")
    annee            = str(extraction.get("annee_estimee") or "")
    description      = str(extraction.get("description_courte", "") or "")
    indices          = [str(i) for i in (extraction.get("indices_visuels", []) or []) if i]
    objets           = [str(o) for o in (extraction.get("objets_importants", []) or []) if o]
    transcript       = str(extraction.get("_transcript_raw", "") or "")

    # ── Niveau 0 : acteur × mots-clés transcript ─────────────────
    # C'est le croisement le plus puissant :
    # "Eddie Murphy bourse" → "Un fauteuil pour deux" en 1 requête
    if acteurs:
        kws = _keywords_from_transcript(transcript)
        for acteur in acteurs[:2]:
            if kws:
                # Requête croisée : acteur + 2 mots-clés transcript
                queries.append(f"{acteur} {' '.join(kws[:2])}")
            # Acteur + genre + année
            if genre and annee:
                queries.append(f"{acteur} {genre} {annee}")
            elif genre:
                queries.append(f"{acteur} {genre}")
            elif annee:
                queries.append(f"{acteur} {annee}")

    # ── Niveau 1 : titres certains ────────────────────────────────
    for titre in titres:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 2 : acteur seul (fallback si croisements ratent) ──
    for acteur in acteurs[:2]:
        queries.append(acteur)
    if len(acteurs) >= 2:
        queries.append(f"{acteurs[0]} {acteurs[1]}")

    # ── Niveau 3 : personnages iconiques ─────────────────────────
    for perso in personnages[:2]:
        queries.append(perso)
        if genre:
            queries.append(f"{perso} {genre}")

    # ── Niveau 4 : objets et indices visuels ─────────────────────
    for item in (objets + indices)[:3]:
        queries.append(item)
        if genre:
            queries.append(f"{item} {genre} {annee}".strip())

    # ── Niveau 5 : titres incertains ─────────────────────────────
    for titre in titres_uncertain:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 6 : description libre ─────────────────────────────
    if description:
        mots = [m for m in re.findall(r"\b\w{4,}\b", description)
                if m.lower() not in _STOPWORDS]
        if mots:
            queries.append(" ".join(mots[:5]))

    # ── Dédoublonnage en conservant l'ordre ──────────────────────
    seen   = set()
    result = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            result.append(q)

    print(f"🔍 Requêtes cascade ({len(result)}): {result[:5]}", flush=True)
    return result


# ════════════════════════════════════════════════════════════════
# BUILD CANDIDATES FROM ACTORS
# Inchangé — appelé en priorité dans app.py avant les requêtes texte
# ════════════════════════════════════════════════════════════════
async def build_candidates_from_actors(extraction: dict, lang: str = "fr") -> list:
    """
    Pour chaque acteur reconnu, récupère sa filmographie TMDB.
    Filtre ensuite par mots-clés transcript pour réduire les candidats.
    Retourne [] si aucun acteur reconnu.
    """
    acteurs = [str(a) for a in (extraction.get("acteurs", []) or []) if a]
    if not acteurs:
        return []

    acteurs = acteurs[:3]
    transcript = str(extraction.get("_transcript_raw", "") or "")
    kws = _keywords_from_transcript(transcript, n=5)

    all_credits: list[list[dict]] = []

    for nom in acteurs:
        try:
            person = await search_person(nom, lang)
            if not person:
                print(f"⚠️ Acteur non trouvé sur TMDB: {nom}", flush=True)
                continue
            credits = await get_person_credits(person["id"], lang)
            if credits:
                print(f"🎭 {nom} → {len(credits)} crédits TMDB", flush=True)
                all_credits.append(credits)
        except Exception as e:
            print(f"⚠️ Erreur crédits acteur {nom}: {e}", flush=True)

    if not all_credits:
        return []

    # ── Intersection si plusieurs acteurs ────────────────────────
    if len(all_credits) >= 2:
        ids_first  = {c["id"] for c in all_credits[0]}
        common_ids = ids_first
        for credits in all_credits[1:]:
            common_ids &= {c["id"] for c in credits}

        if common_ids:
            candidates = [c for c in all_credits[0] if c["id"] in common_ids]
            candidates = sorted(candidates,
                                key=lambda x: x.get("popularity", 0), reverse=True)
            print(f"✅ Intersection acteurs: {len(candidates)} films communs",
                  flush=True)
            # Affiner par mots-clés transcript si dispo
            if kws:
                candidates = _score_by_keywords(candidates, kws) or candidates
            return candidates[:20]

        print("⚠️ Aucune intersection acteurs → union top films", flush=True)

    # ── Union des top crédits (ou acteur unique) ─────────────────
    seen_ids: set = set()
    merged: list  = []
    for credits in all_credits:
        for c in credits[:15]:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                merged.append(c)

    merged = sorted(merged, key=lambda x: x.get("popularity", 0), reverse=True)

    # ── Filtre genre/année ────────────────────────────────────────
    genre = (extraction.get("genre_apparent") or "").lower()
    annee = str(extraction.get("annee_estimee") or "")
    if genre or annee:
        filtered = _filter_by_genre_year(merged, genre, annee)
        if len(filtered) >= 3:
            merged = filtered

    # ── Affiner par mots-clés transcript ─────────────────────────
    # Ex: Eddie Murphy a 149 films — si transcript dit "bourse"
    # on remonte "Un fauteuil pour deux" en tête de liste
    if kws:
        merged = _score_by_keywords(merged, kws) or merged

    print(f"✅ Candidats via acteurs: {len(merged[:20])}", flush=True)
    return merged[:20]


# ════════════════════════════════════════════════════════════════
# HELPERS PRIVÉS
# ════════════════════════════════════════════════════════════════
def _score_by_keywords(candidates: list, keywords: list[str]) -> list:
    """
    Re-trie les candidats en fonction du nombre de mots-clés du transcript
    présents dans leur titre ou synopsis.
    Les candidats sans correspondance restent en queue, triés par popularité.
    """
    kws_lower = [k.lower() for k in keywords]

    def kw_score(c: dict) -> float:
        text = (
            (c.get("title") or c.get("name") or "") + " " +
            (c.get("overview") or "")
        ).lower()
        hits     = sum(1 for kw in kws_lower if kw in text)
        pop      = c.get("popularity", 0)
        return hits * 1000 + pop   # priorité aux hits, tie-break par popularité

    scored = sorted(candidates, key=kw_score, reverse=True)

    # Log si on a reclassé quelque chose
    if scored and scored[0] != candidates[0]:
        top = scored[0]
        print(
            f"🔑 Transcript keywords {keywords} → "
            f"'{top.get('title') or top.get('name')}' remonté en tête",
            flush=True
        )
    return scored


_GENRE_TMDB_IDS = {
    "action":          28,
    "animation":       16,
    "comédie":         35,
    "comedy":          35,
    "crime":           80,
    "documentaire":    99,
    "documentary":     99,
    "drame":           18,
    "drama":           18,
    "fantastique":     14,
    "fantasy":         14,
    "horreur":         27,
    "horror":          27,
    "romance":         10749,
    "science-fiction": 878,
    "scifi":           878,
    "thriller":        53,
    "anime":           16,
}


def _filter_by_genre_year(candidates: list, genre: str, annee: str) -> list:
    genre_id  = _GENRE_TMDB_IDS.get(genre)
    annee_int = int(annee) if annee and annee.isdigit() else None
    result    = []
    for c in candidates:
        if genre_id:
            genres = c.get("genre_ids", [])
            if genres and genre_id not in genres:
                continue
        if annee_int:
            date = c.get("release_date") or c.get("first_air_date") or ""
            year = int(date[:4]) if date and date[:4].isdigit() else None
            if year and abs(year - annee_int) > 3:
                continue
        result.append(c)
    return result


_STOPWORDS = {
    # FR
    "dans", "avec", "pour", "qui", "que", "les", "des", "une", "est",
    "sont", "cette", "leur", "plus", "tout", "mais", "dont", "alors",
    "comme", "quand", "donc", "bien", "très", "aussi", "même", "encore",
    "toujours", "après", "avant", "sous", "entre", "vers", "depuis",
    # EN
    "when", "what", "that", "this", "with", "from", "have", "they",
    "which", "their", "there", "were", "been", "into", "will", "would",
    "could", "should", "about", "after", "before", "some", "your",
    # DE
    "sehr", "wird", "eine", "auch", "oder", "nicht", "mehr", "nach",
    # ES/PT
    "para", "esto", "como", "donde", "tiene", "pero", "todo", "esta",
    # JA/ZH/KO (mots latins résiduels)
    "nani", "kore", "sono",
}