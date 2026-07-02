"""
core/confidence.py — Score de confiance composite.

Le rerank LLM (Gemini/Qwen/Groq) fournit un score auto-déclaré, connu
pour être mal calibré : un LLM qui hallucine le fait souvent avec la
même assurance qu'un LLM qui a raison. Ce module recalcule une confiance
plus fiable en croisant les "avis" indépendants obtenus par chaque canal
de recherche du pipeline (acteurs, cascade TMDB, réplique exacte,
Wikidata, web search) : plus un même candidat est retrouvé par des
canaux indépendants, plus la confiance composite augmente — peu importe
ce qu'un seul LLM déclare sur sa propre certitude.

Utilisation dans process_analysis() :

    opinions = []
    opinions.append(make_opinion(actor_result, "actors"))
    opinions.append(make_opinion(cascade_result, "cascade"))
    opinions.append(make_opinion(quote_result, "quote"))
    opinions.append(make_opinion(wd_result, "wikidata"))
    opinions.append(make_opinion(web_result, "web"))

    ranked = rank_opinions(opinions)
    best         = ranked[0]   # candidat le plus confiant
    alternatives = ranked[1:]  # candidats suivants, pour l'UX multi-choix
"""

from typing import Optional


# Bonus de confiance par source indépendante supplémentaire pointant
# vers le même candidat. Plafonné pour ne jamais atteindre une fausse
# certitude à 100% uniquement par accumulation de canaux corrélés
# (ex: acteurs et cascade partagent souvent la même donnée d'entrée).
AGREEMENT_BONUS_PER_EXTRA_SOURCE = 12
MAX_COMPOSITE_SCORE = 97

# En dessous de ce seuil de confiance composite, le pipeline doit
# proposer des alternatives plutôt qu'un résultat unique affirmé.
MULTI_CANDIDATE_THRESHOLD = 65


def make_opinion(result: Optional[dict], source: str) -> Optional[dict]:
    """Convertit un résultat de rerank (ou None) en 'avis' normalisé."""
    if not result or not result.get("id"):
        return None
    return {
        "id":             result["id"],
        "score":          result.get("score", 0),
        "meilleur_titre": result.get("meilleur_titre", "Inconnu"),
        "media_type":     result.get("media_type", "movie"),
        "source":         source,
    }


def rank_opinions(opinions: list, max_results: int = 3) -> list[dict]:
    """
    Regroupe les avis par id de candidat, calcule un score composite
    (meilleur score brut + bonus d'accord entre sources indépendantes),
    et retourne les candidats triés du plus au moins confiant.

    Chaque élément retourné :
      {
        "id", "meilleur_titre", "media_type",
        "score",            # score composite final (celui à afficher/utiliser)
        "raw_score",        # meilleur score brut d'origine, avant bonus
        "agreement_count",  # nombre de canaux indépendants d'accord
        "sources",          # liste des canaux (["actors", "quote", ...])
      }
    """
    valid = [o for o in opinions if o]
    if not valid:
        return []

    grouped: dict[int, dict] = {}
    for o in valid:
        cid = o["id"]
        if cid not in grouped:
            grouped[cid] = {
                "id":             cid,
                "meilleur_titre": o["meilleur_titre"],
                "media_type":     o["media_type"],
                "best_score":     o["score"],
                "sources":        set(),
            }
        grouped[cid]["sources"].add(o["source"])
        if o["score"] > grouped[cid]["best_score"]:
            grouped[cid]["best_score"]     = o["score"]
            grouped[cid]["meilleur_titre"] = o["meilleur_titre"]

    ranked = []
    for cid, g in grouped.items():
        agreement_count = len(g["sources"])
        composite = g["best_score"] + AGREEMENT_BONUS_PER_EXTRA_SOURCE * (agreement_count - 1)
        composite = min(MAX_COMPOSITE_SCORE, composite)
        ranked.append({
            "id":              cid,
            "meilleur_titre":  g["meilleur_titre"],
            "media_type":      g["media_type"],
            "score":           composite,
            "raw_score":       g["best_score"],
            "agreement_count": agreement_count,
            "sources":         sorted(g["sources"]),
        })

    ranked.sort(key=lambda r: (r["score"], r["agreement_count"]), reverse=True)

    if ranked:
        top = ranked[0]
        print(
            f"🧮 Confiance composite — {top['meilleur_titre']} : "
            f"score={top['score']} (brut={top['raw_score']}, "
            f"accord={top['agreement_count']} sources={top['sources']})",
            flush=True,
        )

    return ranked[:max_results]