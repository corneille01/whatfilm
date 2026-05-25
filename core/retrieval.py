async def build_search_query(extraction):
    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    # 1. On utilise les bonnes clés générées par Gemini en français !
    possible_titles = extraction.get("titres_possibles", [])
    objets = extraction.get("objets_importants", [])
    genre = extraction.get("genre_film_serie", [])

    # 2. STRATÉGIE TMDB :
    # TMDB fonctionne par recherche de titre. On lui envoie en priorité le 
    # premier titre suggéré par l'IA. C'est la meilleure méthode.
    if isinstance(possible_titles, list) and len(possible_titles) > 0:
        return str(possible_titles[0])

    # 3. SOLUTION DE SECOURS :
    # Si l'IA n'a pas trouvé de titre, on tente avec quelques mots-clés très courts.
    terms = []
    if isinstance(objets, list):
        terms += objets
    if isinstance(genre, list):
        terms += genre

    query = " ".join([str(t) for t in terms if t])
    
    # On limite à 50 caractères maximum, sinon TMDB ne trouve rien
    return query[:50]