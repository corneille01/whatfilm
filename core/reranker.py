"""
core/reranker_fixes.py
Patches à appliquer dans core/reranker.py.

3 fixes :
  1. _parse_rerank_response : id=None → prendre le candidat le plus populaire
  2. _rerank_groq : inclure les ids dans le prompt system pour forcer un choix valide
  3. _rerank_groq : system prompt plus directif sur l'obligation de choisir un id
"""

# ─── FIX 1 ────────────────────────────────────────────────────────────
# Remplace _parse_rerank_response dans reranker.py par cette version :

def _parse_rerank_response(text: str, candidates: list) -> dict:
    """
    Parse la réponse LLM.
    - score=0 est accepté (= incertitude, pas erreur)
    - id=None → fallback sur le candidat le plus populaire (pas une erreur bloquante)
    """
    text   = _clean_json_fences(text)
    result = json.loads(text)   # lève JSONDecodeError si tronqué

    if not isinstance(result, dict):
        raise ValueError(f"Réponse non-dict : {type(result)}")

    # id manquant ou None → fallback candidat le plus populaire
    if not result.get("id"):
        best = max(candidates, key=lambda c: c.get("popularity", 0), default=None)
        if best:
            print(
                f"⚠️ Rerank: id=None dans réponse LLM → fallback popularité "
                f"({best.get('title') or best.get('name')})",
                flush=True
            )
            result["id"]             = best["id"]
            result["meilleur_titre"] = best.get("title") or best.get("name") or "Inconnu"
            result["score"]          = min(result.get("score", 30), 30)  # plafonner à 30
            result["raison"]         = (result.get("raison") or "") + " [id fallback popularité]"
        else:
            raise ValueError(f"id manquant et aucun candidat disponible")

    # Vérifier que l'id retourné existe bien dans les candidats
    candidate_ids = {c["id"] for c in candidates}
    if result["id"] not in candidate_ids:
        print(f"⚠️ Rerank: id={result['id']} absent des candidats → rejet", flush=True)
        raise ValueError(f"id={result['id']} absent des candidats")

    # Normaliser meilleur_titre si absent
    if not result.get("meilleur_titre"):
        matched = next(
            (c for c in candidates if c.get("id") == result.get("id")), None
        )
        result["meilleur_titre"] = (
            (matched.get("title") or matched.get("name") or "Inconnu")
            if matched else "Inconnu"
        )

    # score : accepter 0 (incertitude), fallback 50 si clé absente
    if "score" not in result:
        result["score"] = 50

    return result


# ─── FIX 2 ────────────────────────────────────────────────────────────
# Dans _rerank_groq, remplace le bloc "messages" par cette version
# qui injecte les ids valides dans le system prompt :

def _build_groq_messages(prompt: str, candidates: list) -> list:
    """
    Construit les messages pour Groq en injectant les ids valides
    directement dans le system prompt pour éviter id=None.
    """
    valid_ids = [str(c["id"]) for c in candidates[:10]]
    ids_str   = ", ".join(valid_ids)

    return [
        {
            "role": "system",
            "content": (
                "Tu es un expert en cinéma. "
                "Réponds UNIQUEMENT en JSON valide, sans markdown. "
                f"Tu DOIS choisir un id parmi cette liste exacte : [{ids_str}]. "
                "Ne retourne JAMAIS id=null ou un id absent de cette liste. "
                "Si tu n'es pas sûr, choisis l'id le plus probable et mets score entre 20 et 49. "
                "Ne mets score=0 que si aucun candidat ne correspond du tout, "
                "mais tu dois quand même choisir un id valide."
            )
        },
        {"role": "user", "content": prompt}
    ]


# ─── INSTRUCTIONS D'INTÉGRATION ───────────────────────────────────────
"""
Dans core/reranker.py :

1. Remplacer la fonction _parse_rerank_response par la version ci-dessus.

2. Dans _rerank_groq, remplacer :
    "messages": [
        {"role": "system", "content": "Tu es un expert..."},
        {"role": "user", "content": prompt}
    ],
   par :
    "messages": _build_groq_messages(prompt, candidates),

3. Ajouter _build_groq_messages dans le fichier.

4. Dans data/tmdb.py, ajouter les fonctions de tmdb_multilang_patch.py.

5. Dans app.py (ou le fichier qui orchestre la pipeline), remplacer les appels
   search_candidates() + search_tv_candidates() par search_multi_lang().
"""