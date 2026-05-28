"""
core/retrieval.py — Construction de la requête TMDB avec stratégie en cascade
Si le titre exact ne donne rien, on essaie les variantes jusqu'à trouver des candidats.
"""
import re


def _nettoyer(texte: str) -> str:
    """Retire la ponctuation problématique pour TMDB."""
    t = re.sub(r"[\"''\u2018\u2019\u201c\u201d]", "", texte)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _variantes(titre: str) -> list:
    """
    Génère des variantes d'un titre pour maximiser les chances TMDB.
    Ex: "Clanton's Revenge" → ["Clanton's Revenge", "Clantons Revenge", "Clanton Revenge", "Clanton"]
    """
    variantes = [titre]

    sans_apos = _nettoyer(titre)
    if sans_apos != titre:
        variantes.append(sans_apos)

    mots = sans_apos.split()
    if len(mots) >= 3:
        variantes.append(" ".join(mots[:-1]))  # sans le dernier mot
    if len(mots) >= 2:
        variantes.append(mots[0])              # premier mot seul

    seen = set()
    result = []
    for v in variantes:
        v_clean = v.strip()
        if v_clean and v_clean.lower() not in seen:
            seen.add(v_clean.lower())
            result.append(v_clean)
    return result


async def build_search_query(extraction: dict) -> str:
    """Retourne la meilleure requête initiale. Priorité : titre > personnage > acteur."""
    if not isinstance(extraction, dict):
        return str(extraction)[:150]

    titles = [str(t).strip() for t in extraction.get("titres_possibles", []) if t and str(t).strip()]
    chars  = [str(c).strip() for c in extraction.get("personnages", [])       if c and str(c).strip()]
    actors = [str(a).strip() for a in extraction.get("acteurs", [])           if a and str(a).strip()]

    if titles:  return titles[0]
    if chars:   return chars[0]
    if actors:  return actors[0]
    return ""


async def build_cascade_queries(extraction: dict) -> list:
    """
    Retourne une liste ordonnée de requêtes à essayer l'une après l'autre.
    S'arrête à la première qui donne des résultats (logique dans app.py).
    """
    if not isinstance(extraction, dict):
        q = str(extraction)[:150].strip()
        return [q] if q else []

    titles = [str(t).strip() for t in extraction.get("titres_possibles", []) if t and str(t).strip()]
    chars  = [str(c).strip() for c in extraction.get("personnages", [])       if c and str(c).strip()]
    actors = [str(a).strip() for a in extraction.get("acteurs", [])           if a and str(a).strip()]
    desc   = str(extraction.get("description_courte", "") or "").strip()

    queries = []

    # 1. Toutes les variantes de chaque titre proposé par Gemini
    for titre in titles:
        queries.extend(_variantes(titre))

    # 2. Personnages (souvent == titre pour séries/anime)
    for char in chars:
        queries.extend(_variantes(char))

    # 3. Titre + acteur (recherche combinée)
    if titles and actors:
        queries.append(f"{_nettoyer(titles[0])} {actors[0]}")

    # 4. Acteur seul
    for actor in actors:
        queries.append(actor)

    # 5. Mots-clés de la description si tout le reste échoue
    if desc:
        mots_desc = [m for m in desc.split() if len(m) > 4][:5]
        if mots_desc:
            queries.append(" ".join(mots_desc))

    # Dédoublonnage en gardant l'ordre
    seen = set()
    result = []
    for q in queries:
        q_clean = q.strip()
        if q_clean and q_clean.lower() not in seen and len(q_clean) >= 2:
            seen.add(q_clean.lower())
            result.append(q_clean)

    return result