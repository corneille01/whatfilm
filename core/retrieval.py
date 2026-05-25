async def build_search_query(extraction):
    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    # On récupère les listes
    possible_titles = extraction.get("titres_possibles", [])
    personnages = extraction.get("personnages", []) 
    acteurs = extraction.get("acteurs", [])
    
    # 1ère Priorité : Le nom de l'acteur (c'est ce qui marche le mieux sur TMDB)
    if acteurs and len(acteurs) > 0:
        return str(acteurs[0])
        
    # 2ème Priorité : Le nom du personnage
    if personnages and len(personnages) > 0:
        return str(personnages[0])
        
    # 3ème Priorité : Le titre supposé
    if possible_titles and len(possible_titles) > 0:
        return str(possible_titles[0])

    return ""