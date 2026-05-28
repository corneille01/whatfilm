"""
core/retrieval.py — Construction de la requête TMDB
Priorité : titre > titre + acteur > personnage > acteur seul
"""

async def build_search_query(extraction):
    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    possible_titles = extraction.get("titres_possibles", [])
    personnages     = extraction.get("personnages", [])
    acteurs         = extraction.get("acteurs", [])

    # Nettoyage : retire les valeurs vides/None
    titles  = [str(t).strip() for t in possible_titles if t and str(t).strip()]
    actors  = [str(a).strip() for a in acteurs        if a and str(a).strip()]
    chars   = [str(c).strip() for c in personnages     if c and str(c).strip()]

    # 1. Titre seul (le plus fiable pour TMDB)
    if titles:
        return titles[0]

    # 2. Personnage principal (souvent == titre pour les séries)
    if chars:
        return chars[0]

    # 3. Acteur en dernier recours seulement
    if actors:
        return actors[0]

    return ""