"""
core/retrieval.py — Construction des requêtes de recherche TMDB.

Fonctions :
  - build_cascade_queries   : génère une cascade de requêtes à partir de l'extraction
  - build_candidates_from_actors : recherche via filmographie des acteurs reconnus
"""

import re
from data.tmdb import search_person, get_person_credits


# ════════════════════════════════════════════════════════════════
# BUILD CASCADE QUERIES
# ════════════════════════════════════════════════════════════════
async def build_cascade_queries(extraction: dict) -> list[str]:
    """
    Génère une liste de requêtes par ordre de précision décroissante.
    Chaque requête est essayée dans l'ordre jusqu'à obtenir des résultats.
    """
    queries = []

    titres        = [t for t in extraction.get("titres_possibles", []) if t and not str(t).startswith("?")]
    titres_uncertain = [str(t)[1:] for t in extraction.get("titres_possibles", []) if str(t).startswith("?")]
    acteurs       = extraction.get("acteurs", []) or []
    personnages   = extraction.get("personnages", []) or []
    genre         = extraction.get("genre_apparent", "") or ""
    annee         = str(extraction.get("annee_estimee") or "")
    description   = extraction.get("description_courte", "") or ""
    indices       = extraction.get("indices_visuels", []) or []
    objets        = extraction.get("objets_importants", []) or []

    # ── Niveau 1 : titres certains (seuls ou + acteur) ───────────
    for titre in titres:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 2 : acteur + genre + année ────────────────────────
    if acteurs and genre:
        queries.append(f"{acteurs[0]} {genre} {annee}".strip())
    if acteurs:
        queries.append(f"{acteurs[0]} {annee}".strip())
    if len(acteurs) >= 2:
        queries.append(f"{acteurs[0]} {acteurs[1]}")

    # ── Niveau 3 : personnages iconiques ─────────────────────────
    for perso in personnages[:2]:
        queries.append(perso)
        if genre:
            queries.append(f"{perso} {genre}")

    # ── Niveau 4 : objets/indices iconiques ──────────────────────
    for obj in (objets + indices)[:3]:
        queries.append(obj)
        if genre:
            queries.append(f"{obj} {genre} {annee}".strip())

    # ── Niveau 5 : titres incertains ─────────────────────────────
    for titre in titres_uncertain:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 6 : description libre ─────────────────────────────
    if description:
        # Extraire les mots-clés les plus significatifs
        mots = [m for m in re.findall(r"\b\w{4,}\b", description) if m.lower() not in _STOPWORDS]
        if mots:
            queries.append(" ".join(mots[:5]))
        if genre:
            queries.append(f"{description[:60]} {genre}")

    # ── Dédoublonnage en conservant l'ordre ──────────────────────
    seen = set()
    result = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            result.append(q)

    print(f"🔍 Requêtes cascade ({len(result)}): {result[:5]}", flush=True)
    return result


# ════════════════════════════════════════════════════════════════
# BUILD CANDIDATES FROM ACTORS
# ════════════════════════════════════════════════════════════════
async def build_candidates_from_actors(extraction: dict, lang: str = "fr") -> list:
    """
    Pour chaque acteur reconnu dans l'extraction, cherche son profil TMDB
    et récupère sa filmographie. Retourne les films/séries communs aux acteurs
    reconnus (intersection si plusieurs), sinon l'union des top films.

    Retourne [] si aucun acteur reconnu ou si la recherche échoue.
    """
    acteurs = extraction.get("acteurs", []) or []
    if not acteurs:
        return []

    # On limite à 3 acteurs max pour éviter trop d'appels API
    acteurs = acteurs[:3]

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
            continue

    if not all_credits:
        return []

    # ── Intersection si plusieurs acteurs ────────────────────────
    if len(all_credits) >= 2:
        # IDs du 1er acteur
        ids_first = {c["id"] for c in all_credits[0]}
        # Intersection avec les autres
        common_ids = ids_first
        for credits in all_credits[1:]:
            common_ids &= {c["id"] for c in credits}

        if common_ids:
            # Récupérer les entrées complètes depuis le premier acteur
            candidates = [c for c in all_credits[0] if c["id"] in common_ids]
            candidates = sorted(candidates, key=lambda x: x.get("popularity", 0), reverse=True)
            print(f"✅ Intersection acteurs: {len(candidates)} films communs", flush=True)
            return candidates[:20]

        # Pas d'intersection → union des top films de chaque acteur
        print("⚠️ Aucune intersection acteurs → union top films", flush=True)

    # ── Union des top crédits (ou acteur unique) ─────────────────
    seen_ids: set = set()
    merged: list  = []
    for credits in all_credits:
        for c in credits[:15]:  # Top 15 par acteur
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                merged.append(c)

    # Re-trier par popularité
    merged = sorted(merged, key=lambda x: x.get("popularity", 0), reverse=True)

    # ── Filtrer par genre si extraction l'indique ────────────────
    genre = (extraction.get("genre_apparent") or "").lower()
    annee = str(extraction.get("annee_estimee") or "")

    if genre or annee:
        filtered = _filter_by_genre_year(merged, genre, annee)
        if len(filtered) >= 3:
            merged = filtered

    print(f"✅ Candidats via acteurs: {len(merged[:20])}", flush=True)
    return merged[:20]


# ════════════════════════════════════════════════════════════════
# HELPERS PRIVÉS
# ════════════════════════════════════════════════════════════════
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
    "animation":       16,
    "anime":           16,
}

def _filter_by_genre_year(candidates: list, genre: str, annee: str) -> list:
    """Filtre les candidats par genre TMDB et/ou année estimée (±3 ans)."""
    genre_id = _GENRE_TMDB_IDS.get(genre)
    annee_int = int(annee) if annee and annee.isdigit() else None

    result = []
    for c in candidates:
        # Filtre genre
        if genre_id:
            genres = c.get("genre_ids", [])
            if genres and genre_id not in genres:
                continue
        # Filtre année ±3
        if annee_int:
            date = c.get("release_date") or c.get("first_air_date") or ""
            year = int(date[:4]) if date and date[:4].isdigit() else None
            if year and abs(year - annee_int) > 3:
                continue
        result.append(c)
    return result


_STOPWORDS = {
    "dans", "avec", "pour", "qui", "que", "les", "des", "une", "est",
    "sont", "cette", "leur", "plus", "tout", "mais", "dont", "when",
    "what", "that", "this", "with", "from", "have", "they", "which",
    "sehr", "wird", "eine", "auch", "oder", "para", "esto", "como",
    "donde", "tiene",
}