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
MULTI_CANDIDATE_THRESHOLD = 88


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


def rank_opinions(opinions: list, max_results: int = 5) -> list[dict]:
    """
    Regroupe les avis par id de candidat, calcule un score composite
    plus fiable que le score brut du LLM.

    Principe :
      - un seul canal ne peut pas donner une certitude trop élevée ;
      - plusieurs sources indépendantes qui pointent vers le même film augmentent la confiance ;
      - les sources fortes comme quote/web/wikidata renforcent davantage ;
      - les sources faibles/corrélées comme cascade/actors seules restent plafonnées.

    Chaque élément retourné :
      {
        "id", "meilleur_titre", "media_type",
        "score",            # score composite final
        "raw_score",        # meilleur score brut LLM
        "agreement_count",  # nombre de sources d'accord
        "sources",          # liste des sources
      }
    """
    valid = [o for o in opinions if o and o.get("id")]
    if not valid:
        return []

    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _clamp(value: int, low: int = 0, high: int = 100) -> int:
        return max(low, min(high, value))

    # Sources considérées plus fortes car elles apportent une preuve externe.
    strong_sources = {
        "quote",       # réplique exacte / dialogue
        "web",         # recherche web complète
        "web_light",   # corroboration web léger
        "wikidata",    # source structurée externe
    }

    # Sources utiles mais faibles seules, car elles peuvent être corrélées
    # avec les mêmes indices d'entrée ou produire des faux positifs.
    weak_sources = {
        "cascade",
        "actors",
    }

    # Plafonds si UNE SEULE source soutient le résultat.
    # Objectif : ne plus avoir un faux 95 avec sources=['cascade'].
    single_source_caps = {
        "cascade": 78,
        "actors": 80,
        "web_light": 82,
        "web": 84,
        "wikidata": 84,
        "quote": 88,
    }

    grouped: dict[int, dict] = {}

    for o in valid:
        cid = o["id"]
        source = str(o.get("source", "unknown"))
        score = _clamp(_safe_int(o.get("score", 0)))

        if cid not in grouped:
            grouped[cid] = {
                "id": cid,
                "meilleur_titre": o.get("meilleur_titre", "Inconnu"),
                "media_type": o.get("media_type", "movie"),
                "best_score": score,
                "sources": set(),
                "scores": [],
            }

        grouped[cid]["sources"].add(source)
        grouped[cid]["scores"].append(score)

        if score > grouped[cid]["best_score"]:
            grouped[cid]["best_score"] = score
            grouped[cid]["meilleur_titre"] = o.get("meilleur_titre", "Inconnu")
            grouped[cid]["media_type"] = o.get("media_type", "movie")

    ranked = []

    for cid, g in grouped.items():
        sources = set(g["sources"])
        sorted_sources = sorted(sources)
        agreement_count = len(sources)

        raw_score = _clamp(g["best_score"])
        score = raw_score

        has_strong_source = bool(sources & strong_sources)
        has_only_weak_sources = sources.issubset(weak_sources)

        # ── 1. Une seule source : plafonnement anti faux positif ──
        if agreement_count == 1:
            only_source = next(iter(sources))
            cap = single_source_caps.get(only_source, 82)
            score = min(score, cap)

        # ── 2. Deux sources ou plus : bonus d'accord ──────────────
        else:
            extra_sources = agreement_count - 1
            score += AGREEMENT_BONUS_PER_EXTRA_SOURCE * extra_sources

            # Si l'accord vient seulement de sources faibles/corrélées
            # ex: actors + cascade, on évite la fausse certitude.
            if has_only_weak_sources:
                score = min(score, 88)

            # Si au moins une source forte confirme, on autorise plus haut.
            elif has_strong_source:
                if agreement_count == 2:
                    score = min(score, 93)
                else:
                    score = min(score, MAX_COMPOSITE_SCORE)

            # Cas intermédiaire : plusieurs sources, mais pas très fortes.
            else:
                score = min(score, 90)

        # ── 3. Règle finale de sécurité ──────────────────────────
        # Aucun résultat ne doit dépasser 88 si une seule source le soutient.
        # Cela force l'affichage des alternatives côté frontend.
        if agreement_count <= 1:
            score = min(score, 84)

        # Cascade seule = cas le plus dangereux pour les faux positifs.
        if sources == {"cascade"}:
            score = min(score, 78)

        score = _clamp(score, 0, MAX_COMPOSITE_SCORE)

        ranked.append({
            "id": cid,
            "meilleur_titre": g["meilleur_titre"],
            "media_type": g["media_type"],
            "score": score,
            "raw_score": raw_score,
            "agreement_count": agreement_count,
            "sources": sorted_sources,
        })

    # Tri :
    # 1. score composite
    # 2. nombre de sources d'accord
    # 3. score brut
    ranked.sort(
        key=lambda r: (
            r["score"],
            r["agreement_count"],
            r["raw_score"],
        ),
        reverse=True,
    )

    if ranked:
        top = ranked[0]
        print(
            f"🧮 Confiance composite — {top['meilleur_titre']} : "
            f"score={top['score']} "
            f"(brut={top['raw_score']}, "
            f"accord={top['agreement_count']} "
            f"sources={top['sources']})",
            flush=True,
        )

        if top["agreement_count"] <= 1:
            print(
                "⚠️ Confiance plafonnée : une seule source soutient ce résultat. "
                "Les alternatives doivent être affichées si disponibles.",
                flush=True,
            )

    return ranked[:max_results]
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