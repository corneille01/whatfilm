"""
core/retrieval.py — Construction de la requête TMDB avec stratégie en cascade
"""
import re


def _nettoyer(texte: str) -> str:
    t = re.sub(r"[\"''\u2018\u2019\u201c\u201d]", "", texte)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _variantes(titre: str) -> list:
    variantes = [titre]
    sans_apos = _nettoyer(titre)
    if sans_apos != titre:
        variantes.append(sans_apos)
    mots = sans_apos.split()
    if len(mots) >= 3:
        variantes.append(" ".join(mots[:-1]))
    if len(mots) >= 2:
        variantes.append(mots[0])
    seen = set()
    result = []
    for v in variantes:
        v_clean = v.strip()
        if v_clean and v_clean.lower() not in seen:
            seen.add(v_clean.lower())
            result.append(v_clean)
    return result


async def build_search_query(extraction: dict) -> str:
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
    if not isinstance(extraction, dict):
        q = str(extraction)[:150].strip()
        return [q] if q else []

    titles = [str(t).strip() for t in extraction.get("titres_possibles", []) if t and str(t).strip()]
    chars  = [str(c).strip() for c in extraction.get("personnages", [])       if c and str(c).strip()]
    actors = [str(a).strip() for a in extraction.get("acteurs", [])           if a and str(a).strip()]
    desc   = str(extraction.get("description_courte", "") or "").strip()

    queries = []

    # 1. Titres (le ? est nettoyé avant d'envoyer à TMDB)
    for titre in titles:
        clean = titre.lstrip("?").strip()
        queries.extend(_variantes(clean))

    # 2. Personnages
    for char in chars:
        queries.extend(_variantes(char))

    # 3. Titre + acteur
    if titles and actors:
        queries.append(f"{_nettoyer(titles[0].lstrip('?'))} {actors[0]}")

    # 4. Acteur seul
    for actor in actors:
        queries.append(actor)

    # 5. Mots-clés description
    if desc:
        mots_desc = [m for m in desc.split() if len(m) > 4][:5]
        if mots_desc:
            queries.append(" ".join(mots_desc))

    # 5b. Si chaîne TV détectée dans la description, query ciblée
    chaines = ["TCM", "Canal+", "Netflix", "Arte", "M6", "TF1", "France"]
    for chaine in chaines:
        if chaine.lower() in desc.lower():
            desc_sans_chaine = re.sub(chaine, "", desc, flags=re.IGNORECASE).strip()
            mots = [m for m in desc_sans_chaine.split() if len(m) > 4][:6]
            if mots:
                queries.append(" ".join(mots))
            break

    # Dédoublonnage
    seen = set()
    result = []
    for q in queries:
        q_clean = q.strip()
        if q_clean and q_clean.lower() not in seen and len(q_clean) >= 2:
            seen.add(q_clean.lower())
            result.append(q_clean)

    return result