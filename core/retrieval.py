"""
core/retrieval.py — Construction des requêtes de recherche TMDB.

Stratégie multi-langue :
  1. Langue de la transcription  → priorité maximale (langue du film)
  2. Langue du navigateur        → priorité secondaire (affichage utilisateur)
  3. Anglais                     → fallback universel

Fonctions principales :
  - build_cascade_queries        : génère les requêtes par ordre de précision
  - run_cascade_search           : exécute la cascade avec stratégie multi-langue
  - build_candidates_from_actors : candidats via crédits acteurs TMDB
"""

import re
import asyncio
import os 

from data.tmdb import (
    search_person, get_person_credits, search_multi_lang,
    search_episode_parent_series,
)


# ════════════════════════════════════════════════════════════════
# MAPPING FR → EN POUR LES INDICES VISUELS
# ════════════════════════════════════════════════════════════════

_FR_TO_EN_VISUAL: dict[str, str] = {
    # Tenues / costumes
    "robe de moine":                    "monk robe",
    "robe moine":                       "monk robe",
    "robe de chambre":                  "bathrobe",
    "tenue traditionnelle":             "traditional costume",
    "vêtements traditionnels japonais": "japanese traditional clothing",
    "kimono":                           "kimono",
    "uniforme scolaire":                "school uniform",
    "uniforme militaire":               "military uniform",
    "costume médiéval":                 "medieval costume",
    "armure":                           "armor",
    "cape":                             "cape",
    "masque":                           "mask",
    # Lieux / décors
    "jardin japonais":                  "japanese garden",
    "temple japonais":                  "japanese temple",
    "château japonais":                 "japanese castle",
    "école japonaise":                  "japanese school",
    "château médiéval":                 "medieval castle",
    "forêt":                            "forest",
    "désert":                           "desert",
    "plage":                            "beach",
    "montagne":                         "mountain",
    "ville futuriste":                  "futuristic city",
    "espace":                           "outer space",
    "laboratoire":                      "laboratory",
    "prison":                           "prison",
    "arène":                            "arena",
    "temple":                           "temple",
    "pagode":                           "pagoda",
    "intérieur sombre":                 "dark interior",
    "cave":                             "basement",
    "sous-sol":                         "basement",
    "entrepôt":                         "warehouse",
    "usine abandonnée":                 "abandoned factory",
    "couloir":                          "corridor",
    "tunnel":                           "tunnel",
    "cellule":                          "cell",
    "cage":                             "cage",
    "hangar":                           "hangar",
    "manoir":                           "mansion",
    "château abandonné":                "abandoned castle",
    "maison hantée":                    "haunted house",
    "hôpital abandonné":                "abandoned hospital",
    "école abandonnée":                 "abandoned school",
    "bateau":                           "ship",
    "sous-marin":                       "submarine",
    "vaisseau spatial":                 "spaceship",
    "station spatiale":                 "space station",
    "bunker":                           "bunker",
    "abri":                             "shelter",
    # Objets / accessoires
    "flèche":                           "arrow",
    "arc":                              "bow",
    "épée":                             "sword",
    "katana":                           "katana",
    "éventail":                         "fan",
    "valise rouge":                     "red suitcase",
    "valise":                           "suitcase",
    "pistolet":                         "gun",
    "fusil":                            "rifle",
    "couteau":                          "knife",
    "bouclier":                         "shield",
    "lance":                            "spear",
    "baguette magique":                 "magic wand",
    "grimoire":                         "spellbook",
    "parchemin":                        "scroll",
    "lanterne":                         "lantern",
    "bague":                            "ring",
    "collier":                          "necklace",
    "carte":                            "map",
    "corde":                            "rope",
    "cordes":                           "ropes",
    "chaîne":                           "chain",
    "chaînes":                          "chains",
    "menottes":                         "handcuffs",
    "hache":                            "axe",
    "marteau":                          "hammer",
    "scie":                             "saw",
    "seringue":                         "syringe",
    "masque à gaz":                     "gas mask",
    "combinaison":                      "hazmat suit",
    "logo bbc":                         "BBC logo",
    "logo netflix":                     "Netflix logo",
    "logo hbo":                         "HBO logo",
    "logo amazon":                      "Amazon logo",
    # Personnages / archétypes
    "samouraï":                         "samurai",
    "ninja":                            "ninja",
    "moine":                            "monk",
    "guerrier":                         "warrior",
    "sorcier":                          "wizard",
    "chevalier":                        "knight",
    "geisha":                           "geisha",
    "fantôme":                          "ghost",
    "vampire":                          "vampire",
    "zombie":                           "zombie",
    "alien":                            "alien",
    "robot":                            "robot",
    "dragon":                           "dragon",
    "monstre":                          "monster",
    "créature":                         "creature",
    "créature pendue":                  "hanging creature",
    "créature marine":                  "sea creature",
    "créature humanoïde":               "humanoid creature",
    "démon":                            "demon",
    "sorcière":                         "witch",
    "loup-garou":                       "werewolf",
    "zombie":                           "zombie",
    "mutant":                           "mutant",
    "extraterrestre":                   "alien",
    # Actions / concepts visuels
    "arts martiaux":                    "martial arts",
    "combat":                           "fight",
    "magie":                            "magic",
    "explosion":                        "explosion",
    "course poursuite":                 "car chase",
    "enquête":                          "investigation",
    "enquêteur":                        "detective",
    "fantaisie":                        "fantasy",
    "science-fiction":                  "science fiction",
    "pendu":                            "hanging",
    "pendue":                           "hanging",
    "suspendu":                         "suspended",
    "suspendue":                        "suspended",
    "attaché":                          "tied up",
    "attachée":                         "tied up",
    "torturé":                          "tortured",
    "poursuite":                        "chase",
    "fuite":                            "escape",
    "survie":                           "survival",
    "apocalypse":                       "apocalypse",
    "invasion":                         "invasion",
    "possession":                       "possession",
    "exorcisme":                        "exorcism",
    "enquête criminelle":               "criminal investigation",
    "meurtre":                          "murder",
    "serial killer":                    "serial killer",
    # Éléments narratifs / descriptifs
    "crâne rasé":                       "shaved head",
    "tête rasée":                       "shaved head",
    "homme crâne rasé":                 "shaved head man",
    "bannière rouge":                   "red banner",
    "bannière rouge caractères japonais": "red banner japanese",
    "femme asiatique":                  "asian woman",
    "jardin verdoyant":                 "lush garden",
    "petite amie":                      "girlfriend",
    "petit ami":                        "boyfriend",
    "attrape":                          "catches",
    "vole":                             "flies",
    "homme en t-shirt":                 "man in t-shirt",
    "tire sur une corde":               "pulling rope",
    "tire la corde":                    "pulling rope",
    "salle rustique":                   "rustic room",
    "pièce sombre":                     "dark room",
    "homme barbu":                      "bearded man",
    "femme blonde":                     "blonde woman",
    "enfant seul":                      "child alone",
    "groupe d'adolescents":             "group of teenagers",
    "couple":                           "couple",
    "famille":                          "family",
    "ambiance années 80":               "1980s setting",
    "ambiance années 90":               "1990s setting",
    "époque victorienne":               "victorian era",
    "époque médiévale":                 "medieval era",
    "guerre mondiale":                  "world war",
    "post-apocalyptique":               "post-apocalyptic",
    "dystopie":                         "dystopia",
}

# ════════════════════════════════════════════════════════════════
# MAPPING FR → JP POUR LES INDICES VISUELS JAPONAIS
# ════════════════════════════════════════════════════════════════

_JP_VISUAL_TERMS: dict[str, str] = {
    "kimono":                           "着物",
    "robe de moine":                    "僧侶",
    "moine":                            "僧侶",
    "samouraï":                         "侍",
    "ninja":                            "忍者",
    "geisha":                           "芸者",
    "guerrier":                         "武士",
    "arts martiaux":                    "武道",
    "katana":                           "刀",
    "vêtements traditionnels japonais": "和服",
    "homme crâne rasé":                 "坊主",
    "crâne rasé":                       "坊主",
    "jardin japonais":                  "日本庭園",
    "temple japonais":                  "寺",
    "château japonais":                 "城",
    "pagode":                           "塔",
    "flèche":                           "矢",
    "arc":                              "弓",
    "épée":                             "剣",
    "bannière rouge":                   "赤い旗",
    "lanterne":                         "提灯",
    "combat":                           "戦い",
    "fantôme":                          "幽霊",
    "magie":                            "魔法",
    "dragon":                           "龍",
}

_JP_SIGNAL_TERMS = {
    "jardin japonais", "temple japonais", "château japonais", "école japonaise",
    "pagode", "kimono", "samouraï", "ninja", "geisha", "katana",
    "vêtements traditionnels japonais", "bannière rouge caractères japonais",
    "style anime", "anime", "caractères japonais", "homme crâne rasé",
    "robe de moine",
}

_GENERIC_GENRES = {
    "film-action", "film-drame", "film-thriller", "film-romance",
    "film-comédie", "action", "drame", "thriller", "romance", "comédie",
    "série", "série-animation",
}


def _translate_clue(clue: str) -> str | None:
    clue_lower = clue.lower().strip()
    for fr_key in sorted(_FR_TO_EN_VISUAL, key=len, reverse=True):
        if fr_key in clue_lower:
            return _FR_TO_EN_VISUAL[fr_key]
    return None


def _translate_text(text: str) -> list[str]:
    if not text:
        return []
    text_lower = text.lower()
    found: list[str] = []
    seen_en: set[str] = set()
    for fr_key in sorted(_FR_TO_EN_VISUAL, key=len, reverse=True):
        if fr_key in text_lower:
            en_val = _FR_TO_EN_VISUAL[fr_key]
            if en_val not in seen_en:
                seen_en.add(en_val)
                found.append(en_val)
    return found


def _is_japanese_content(all_clues: list, description: str, indices: list) -> bool:
    all_text = " ".join(all_clues + indices + [description]).lower()
    matches = sum(1 for term in _JP_SIGNAL_TERMS if term in all_text)
    return matches >= 2


def _get_jp_terms(all_clues: list, description: str, indices: list) -> list[str]:
    all_text = " ".join(all_clues + indices + [description]).lower()
    jp_terms = []
    seen: set[str] = set()
    for fr_key in sorted(_JP_VISUAL_TERMS, key=len, reverse=True):
        if fr_key in all_text:
            jp_val = _JP_VISUAL_TERMS[fr_key]
            if jp_val not in seen:
                seen.add(jp_val)
                jp_terms.append(jp_val)
    return jp_terms


# ════════════════════════════════════════════════════════════════
# RÉSOLUTION DYNAMIQUE ÉPISODE → SÉRIE PARENTE
# ════════════════════════════════════════════════════════════════

async def _resolve_episode_to_series(
    titres_incertains_precis: list,
    lang: str = "en",
) -> list[str]:
    """
    Pour chaque titre incertain précis de 2+ mots, tente de trouver
    la série parente via TMDB search_episode_parent_series.

    Pas de dictionnaire statique — couvre toutes les séries TMDB
    dans toutes les langues, y compris les nouvelles sorties.

    Retourne une liste de noms de séries parentes confirmées.
    """
    series_found: list[str] = []
    seen: set[str] = set()

    for titre in titres_incertains_precis[:2]:
        if len(titre.split()) < 2:
            continue  # titre d'un seul mot → probablement pas un épisode
        try:
            candidates = await search_episode_parent_series(titre, lang)
            for c in candidates:
                if c.get("_episode_match") and c.get("name"):
                    serie_name = c["name"]
                    if serie_name not in seen:
                        seen.add(serie_name)
                        series_found.append(serie_name)
                        print(
                            f"📺 Résolution dynamique: '{titre}' → '{serie_name}'",
                            flush=True
                        )
        except Exception as e:
            print(f"⚠️ _resolve_episode_to_series: {e}", flush=True)

    return series_found


# ════════════════════════════════════════════════════════════════
# BUILD CASCADE QUERIES
# ════════════════════════════════════════════════════════════════

async def build_cascade_queries(extraction: dict) -> list[tuple[int, str]]:
    """
    Génère une liste de requêtes par ordre de précision décroissante.
    Chaque requête est taguée avec son niveau (tier) de fiabilité :
    plus le chiffre est bas, plus l'évidence qui l'a produite est forte.
    Ce tier suit le candidat TMDB correspondant jusqu'au reranker, pour
    qu'un match trouvé uniquement via un indice générique (tier 8) ne
    soit jamais traité comme équivalent à un match sur titre certain
    (tier 1) — même si TMDB le retourne comme plus "populaire".

      - Tier 1  : titres certains, titres incertains précis, résolution
                  épisode → série, variantes "series/episode"
      - Tier 2  : acteurs connus
      - Tier 3  : personnages
      - Tier 4  : combinaisons indices_visuels + objets (FR + EN)
      - Tier 5  : mots-clés description_courte (FR + EN + JP)
      - Tier 6  : titres incertains vagues
      - Tier 7  : spécifiques au type de média (anime, documentaire)
      - Tier 8  : indices seuls (dernier recours)
    """
    titres_certains          = []
    titres_incertains_precis = []
    titres_incertains        = []

    for t in extraction.get("titres_possibles", []):
        t = str(t).strip()
        if not t:
            continue
        if t.startswith("?"):
            titre_clean = t[1:].strip()
            if not titre_clean:
                continue
            is_precise = (
                re.search(r'(?<=[a-z])[A-Z]', titre_clean)
                or re.search(r'[,&:\d\-]', titre_clean)
                or (
                    len(titre_clean.split()) >= 2
                    and any(w[0].isupper() for w in titre_clean.split()[1:] if w)
                )
                or (len(titre_clean.split()) == 1 and titre_clean[0].isupper())
            )
            if is_precise:
                titres_incertains_precis.append(titre_clean)
            else:
                titres_incertains.append(titre_clean)
        else:
            titres_certains.append(t)

    acteurs     = extraction.get("acteurs",     []) or []
    personnages = extraction.get("personnages",  []) or []
    genre       = (extraction.get("genre_apparent", "") or "").strip()
    annee       = str(extraction.get("annee_estimee") or "").strip()
    description = (extraction.get("description_courte", "") or "").strip()
    indices     = extraction.get("indices_visuels",   []) or []
    objets      = extraction.get("objets_importants", []) or []

    genre_en = genre.replace("film-", "").replace("série", "series").strip()

    queries: list[tuple[int, str]] = []

    # ── Niveau 1 : titres certains ───────────────────────────────
    for titre in titres_certains:
        queries.append((1, titre))
        if acteurs:
            queries.append((1, f"{titre} {acteurs[0]}"))
        if annee:
            queries.append((1, f"{titre} {annee}"))

    # ── Niveau 1b : titres incertains précis ─────────────────────
    for titre in titres_incertains_precis:
        queries.append((1, titre))
        if annee:
            queries.append((1, f"{titre} {annee}"))
        if acteurs:
            queries.append((1, f"{titre} {acteurs[0]}"))

    # ── Niveau 1b+ : résolution dynamique épisode → série parente ─
    # Déclenché uniquement si des titres incertains précis de 2+ mots existent.
    # Pas de dictionnaire statique : TMDB cherche dynamiquement.
    # Coût : 1 appel /search/tv + max 3×5 appels /season (si épisode trouvé).
    # Déclenchement conditionnel pour éviter les appels inutiles sur les films.
    titres_multi_mots = [t for t in titres_incertains_precis if len(t.split()) >= 2]
    if titres_multi_mots:
        series_parentes = await _resolve_episode_to_series(titres_multi_mots, lang="en")
        existing = {q for _, q in queries}
        for serie in series_parentes:
            if serie not in existing:
                queries.insert(0, (1, serie))  # priorité maximale → première requête

    # ── Niveau 1c : titres incertains précis + "series/episode" ──
    for titre in titres_incertains_precis:
        if len(titre.split()) >= 3:
            queries.append((1, f"{titre} series"))
            queries.append((1, f"{titre} episode"))

    # ── Niveau 2 : acteurs ───────────────────────────────────────
    if acteurs:
        queries.append((2, f"{acteurs[0]} {genre} {annee}".strip()))
        queries.append((2, acteurs[0]))
    if len(acteurs) >= 2:
        queries.append((2, f"{acteurs[0]} {acteurs[1]}"))

    # ── Niveau 3 : personnages ───────────────────────────────────
    for perso in personnages[:2]:
        queries.append((3, f"{perso} {genre}".strip()))

    # ── Niveau 4 : combinaisons indices + objets (FR + EN) ───────
    all_clues = [o for o in objets if o] + [i for i in indices if i]

    all_clues_en: list[str] = []
    seen_en_clues: set[str] = set()
    for c in all_clues:
        translated = _translate_clue(c)
        if translated and translated not in seen_en_clues:
            seen_en_clues.add(translated)
            all_clues_en.append(translated)

    if len(all_clues) >= 2:
        for i in range(min(3, len(all_clues) - 1)):
            pair = f"{all_clues[i]} {all_clues[i+1]}"
            queries.append((4, pair))
            if genre:
                queries.append((4, f"{pair} {genre}"))
            if annee:
                queries.append((4, f"{pair} {annee}"))

    if len(all_clues) >= 3:
        triple = f"{all_clues[0]} {all_clues[1]} {all_clues[2]}"
        queries.append((4, triple))
        if genre:
            queries.append((4, f"{triple} {genre}"))

    if len(all_clues_en) >= 2:
        for i in range(min(2, len(all_clues_en) - 1)):
            pair_en = f"{all_clues_en[i]} {all_clues_en[i+1]}"
            queries.append((4, pair_en))
            if genre_en:
                queries.append((4, f"{pair_en} {genre_en}"))

    for clue_en in all_clues_en[:3]:
        queries.append((4, clue_en))

    # ── Niveau 5 : mots-clés description_courte (FR) ─────────────
    if description:
        keywords = _extract_keywords(description)
        if len(keywords) >= 3:
            queries.append((5, " ".join(keywords[:4])))
            if genre:
                queries.append((5, f"{' '.join(keywords[:3])} {genre}"))
            if annee:
                queries.append((5, f"{' '.join(keywords[:3])} {annee}"))
        proper_nouns = _extract_proper_nouns(description)
        for noun in proper_nouns[:2]:
            queries.append((5, noun))
            if genre:
                queries.append((5, f"{noun} {genre}"))

    # ── Niveau 5b : termes EN depuis description FR ───────────────
    if description:
        desc_en_terms = _translate_text(description)
        if desc_en_terms:
            queries.append((5, " ".join(desc_en_terms[:3])))
            if genre_en:
                queries.append((5, f"{' '.join(desc_en_terms[:2])} {genre_en}"))
            if annee:
                queries.append((5, f"{' '.join(desc_en_terms[:2])} {annee}"))

    # ── Niveau 5c : requêtes japonaises si contenu JP détecté ─────
    if _is_japanese_content(all_clues, description, indices):
        jp_terms = _get_jp_terms(all_clues, description, indices)
        if jp_terms:
            print(f"🇯🇵 Contenu japonais détecté → requêtes JP: {jp_terms[:3]}", flush=True)
            if len(jp_terms) >= 2:
                queries.append((5, f"{jp_terms[0]} {jp_terms[1]}"))
            queries.append((5, jp_terms[0]))
            if annee:
                queries.append((5, f"{jp_terms[0]} {annee}"))
            if all_clues_en:
                queries.append((5, f"{all_clues_en[0]} japanese"))
                if genre_en:
                    queries.append((5, f"japanese {genre_en} {annee}".strip()))

    # ── Niveau 6 : titres incertains vagues ──────────────────────
    for titre in titres_incertains:
        queries.append((6, titre))
        if acteurs:
            queries.append((6, f"{titre} {acteurs[0]}"))

    # ── Niveau 7 : spécifiques au type de média ──────────────────
    if genre in ("anime", "serie-animation", "serie-animée"):
        for titre in (titres_certains + titres_incertains_precis + titres_incertains)[:2]:
            queries.append((7, f"{titre} anime"))
        for perso in personnages[:1]:
            queries.append((7, f"{perso} anime"))
        for clue_en in all_clues_en[:2]:
            queries.append((7, f"{clue_en} anime"))

    if "document" in genre:
        for titre in titres_certains[:2]:
            queries.append((7, f"{titre} documentary"))
        mots_doc = [
            m for m in re.findall(r"\b\w{5,}\b", description)
            if m.lower() not in _STOPWORDS
        ]
        if mots_doc:
            queries.append((7, f"{' '.join(mots_doc[:3])} documentary"))

    # ── Niveau 8 : indices seuls (dernier recours) ───────────────
    for clue in all_clues[:3]:
        if len(clue) > 8:
            queries.append((8, clue))

    # ── Dédoublonnage (garde le tier le plus fort en cas de doublon) ──
    best_tier: dict[str, int] = {}
    order: list[str] = []
    for tier, q in queries:
        q = q.strip()
        if not q or len(q) <= 2:
            continue
        if q not in best_tier:
            best_tier[q] = tier
            order.append(q)
        elif tier < best_tier[q]:
            best_tier[q] = tier

    result = [(best_tier[q], q) for q in order]
    print(f"🔍 Requêtes cascade ({len(result)}): {[q for _, q in result[:6]]}", flush=True)
    return result
# ════════════════════════════════════════════════════════════════
# RUN CASCADE SEARCH
# ════════════════════════════════════════════════════════════════

async def run_cascade_search(
    extraction: dict,
    transcript_lang: str | None = None,
    browser_lang: str | None = None,
    max_candidates: int = 20,
) -> list:
    if not transcript_lang:
        transcript_lang = extraction.get("langue_originale") or None

    queries = await build_cascade_queries(extraction)

    titres_certains = {
        str(t).strip()
        for t in extraction.get("titres_possibles", [])
        if t and not str(t).startswith("?")
    }

    titres_precis = {
        str(t)[1:].strip()
        for t in extraction.get("titres_possibles", [])
        if str(t).startswith("?")
        and (
            re.search(r'(?<=[a-z])[A-Z]|[,&:\d\-]', str(t)[1:])
            or (
                len(str(t)[1:].split()) >= 2
                and any(w[0].isupper() for w in str(t)[1:].split()[1:] if w)
            )
        )
    }

    seen_ids:   set  = set()
    candidates: list = []

    for tier, query in queries:
        if len(candidates) >= max_candidates:
            break

        effective_transcript_lang = transcript_lang

        if re.search(r'[぀-ゟ゠-ヿ一-鿿]', query):
            effective_transcript_lang = "ja"
        elif re.search(r'[가-힯ᄀ-ᇿ]', query):
            effective_transcript_lang = "ko"
        elif re.search(r'[一-鿿]', query) and not re.search(r'[぀-ゟ゠-ヿ]', query):
            effective_transcript_lang = "zh"
        elif (
            transcript_lang not in (None, "en")
            and re.fullmatch(r'[a-zA-Z0-9 \-]+', query)
        ):
            effective_transcript_lang = "en"

        results = await search_multi_lang(
            query,
            transcript_lang=effective_transcript_lang,
            browser_lang=browser_lang,
        )

        added = 0
        for item in results:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                # Tier le plus fort (chiffre le plus bas) qui a produit ce
                # candidat — utilisé pour le tri et transmis au reranker
                # pour qu'il ne traite pas un match générique (tier 8)
                # comme équivalent à un match sur titre certain (tier 1),
                # même si le candidat est très populaire sur TMDB.
                item["_match_tier"] = tier
                candidates.append(item)
                added += 1
            elif item_id:
                for c in candidates:
                    if c.get("id") == item_id and tier < c.get("_match_tier", 99):
                        c["_match_tier"] = tier
                        break

        if added > 0:
            print(
                f"  ↳ '{query}' (tier {tier}) → +{added} candidats "
                f"(total={len(candidates)})",
                flush=True
            )

        if query in titres_certains and len(candidates) >= 3:
            print(f"⚡ Early stop : titre certain '{query}' trouvé", flush=True)
            break

        if query in titres_precis and len(candidates) >= 2:
            print(f"⚡ Early stop : titre précis '{query}' trouvé", flush=True)
            break

    # Tri par fiabilité d'abord (tier ascendant = évidence plus forte),
    # popularité seulement en départage à l'intérieur d'un même tier.
    # Avant ce fix, le tri était fait uniquement par popularité, ce qui
    # faisait remonter des films populaires mais non pertinents (trouvés
    # via une requête générique de niveau 4-8) devant des candidats plus
    # obscurs mais bien plus probants.
    candidates.sort(key=lambda x: (x.get("_match_tier", 99), -x.get("popularity", 0)))
    print(
        f"📋 Cascade terminée → {len(candidates)} candidats uniques",
        flush=True
    )
    return candidates[:max_candidates]


# ════════════════════════════════════════════════════════════════
# BUILD CANDIDATES FROM ACTORS
# ════════════════════════════════════════════════════════════════

# IDs de genres TMDB à exclure de l'intersection acteurs
# (talk-shows, reality, actualités — faux positifs fréquents)
_EXCLUDE_GENRE_IDS = {
    10767,  # Talk
    10763,  # News
    10764,  # Reality
    10766,  # Soap
}


async def build_candidates_from_actors(
    extraction: dict,
    lang: str = "fr",
) -> list:
    """
    Construit des candidats TMDB à partir des acteurs reconnus.

    Version renforcée anti-hallucination :
    - seuil acteur par défaut : 90 ;
    - les certitudes manquantes valent 0, donc rejetées ;
    - les chaînes "95" ou "95%" sont bien converties ;
    - on limite aux 3 meilleurs acteurs fiables ;
    - on exclut talk-shows, news, reality et soaps.
    """
    acteurs = extraction.get("acteurs", []) or []
    certitudes = extraction.get("acteurs_certitude", []) or []
    source = str(extraction.get("source", "") or "").lower()

    if not acteurs:
        return []

    min_cert = int(os.environ.get("ACTOR_MIN_CERT", "90"))
    max_actors = int(os.environ.get("ACTOR_SEARCH_MAX_ACTORS", "3"))

    def _to_cert(value) -> int:
        """
        Convertit proprement :
        95      → 95
        "95"    → 95
        "95%"   → 95
        None    → 0
        invalide → 0
        """
        try:
            if value is None:
                return 0

            if isinstance(value, (int, float)):
                return int(value)

            s = str(value).strip().replace("%", "")
            if not s:
                return 0

            return int(float(s))

        except Exception:
            return 0

    # Aligne la longueur des certitudes sur celle des acteurs.
    # Important : une certitude absente vaut 0, pas 75.
    certitudes = list(certitudes)
    while len(certitudes) < len(acteurs):
        certitudes.append(0)

    certitudes = certitudes[:len(acteurs)]

    acteurs_valides = []

    for acteur, certitude_raw in zip(acteurs, certitudes):
        acteur = str(acteur or "").strip()
        if not acteur:
            continue

        certitude = _to_cert(certitude_raw)

        if certitude >= min_cert:
            acteurs_valides.append(acteur)

            print(
                f"✅ Acteur accepté: '{acteur}' "
                f"(certitude={certitude}>={min_cert}, source={source!r})",
                flush=True,
            )

        else:
            print(
                f"⚠️ Acteur rejeté — certitude trop faible: '{acteur}' "
                f"(certitude={certitude}<{min_cert}, source={source!r})",
                flush=True,
            )

    if not acteurs_valides:
        print(
            f"⚠️ Aucun acteur fiable → skip recherche par acteurs. "
            f"Acteurs originaux: {list(zip(acteurs, certitudes))}",
            flush=True,
        )
        return []

    acteurs = acteurs_valides[:max_actors]
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

    # ── Intersection multi-acteurs ───────────────────────────────
    if len(all_credits) >= 2:
        ids_first = {c["id"] for c in all_credits[0]}
        common_ids = ids_first

        for credits in all_credits[1:]:
            common_ids &= {c["id"] for c in credits}

        if common_ids:
            candidates = [
                c for c in all_credits[0]
                if c["id"] in common_ids
            ]

            filtered_intersection = [
                c for c in candidates
                if not _EXCLUDE_GENRE_IDS.intersection(
                    set(c.get("genre_ids", []))
                )
            ]

            if filtered_intersection:
                filtered_intersection = sorted(
                    filtered_intersection,
                    key=lambda x: x.get("popularity", 0),
                    reverse=True,
                )

                print(
                    f"✅ Intersection acteurs: {len(filtered_intersection)} films communs "
                    f"({len(candidates) - len(filtered_intersection)} talk-shows exclus)",
                    flush=True,
                )

                return filtered_intersection[:20]

            print(
                f"⚠️ Intersection acteurs = {len(candidates)} résultats, "
                "tous des talk-shows/reality/news → ignorée, passage à l'union",
                flush=True,
            )

        else:
            print("⚠️ Aucune intersection acteurs → union top films", flush=True)

    # ── Union fallback ───────────────────────────────────────────
    seen_ids: set = set()
    merged: list = []

    for credits in all_credits:
        for c in credits[:30]:
            item_id = c.get("id")

            if not item_id or item_id in seen_ids:
                continue

            seen_ids.add(item_id)
            merged.append(c)

    # Exclure talk-shows, news, reality, soaps.
    merged = [
        c for c in merged
        if not _EXCLUDE_GENRE_IDS.intersection(
            set(c.get("genre_ids", []))
        )
    ]

    merged = sorted(
        merged,
        key=lambda x: x.get("popularity", 0),
        reverse=True,
    )

    genre = (extraction.get("genre_apparent") or "").lower()
    annee = str(extraction.get("annee_estimee") or "")

    genre_is_generic = genre in _GENERIC_GENRES or not genre

    if (genre or annee) and not genre_is_generic:
        filtered = _filter_by_genre_year(merged, genre, annee)

        if len(filtered) >= 3:
            print(
                f"🔍 Filtre genre/année appliqué : "
                f"{len(merged)} → {len(filtered)} candidats",
                flush=True,
            )
            merged = filtered

    elif genre_is_generic and (genre or annee):
        print(
            f"ℹ️ Genre '{genre}' trop générique → filtre désactivé "
            "(évite d'exclure les séries TV)",
            flush=True,
        )

    for c in merged:
        if "media_type" not in c:
            c["media_type"] = "tv" if c.get("first_air_date") else "movie"

    print(f"✅ Candidats via acteurs: {len(merged[:20])}", flush=True)

    return merged[:20]

# ════════════════════════════════════════════════════════════════
# HELPERS PRIVÉS
# ════════════════════════════════════════════════════════════════

_STOPWORDS = {
    "dans", "avec", "pour", "qui", "que", "les", "des", "une", "est",
    "sont", "cette", "leur", "plus", "tout", "mais", "dont", "elle",
    "lui", "ils", "elles", "nous", "vous", "très", "bien", "même",
    "aussi", "comme", "quand", "alors", "après", "avant", "jusqu",
    "entre", "contre", "sans", "sous", "sur", "par", "depuis",
    "when", "what", "that", "this", "with", "from", "have", "they",
    "which", "been", "were", "their", "there", "about", "would",
    "could", "should", "other", "into", "than", "then", "some",
    "sehr", "wird", "eine", "auch", "oder", "para", "esto", "como",
    "donde", "tiene", "pero", "porque", "uma", "isso", "este",
    "film", "scene", "scène", "vidéo", "video", "homme", "femme",
    "jeune", "vieux", "grand", "petit", "faire", "aller", "venir",
    "voir", "dire", "avoir", "être",
}


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"\b\w{4,}\b", text, re.UNICODE)
    result = []
    seen   = set()
    for w in words:
        w_lower = w.lower()
        if w_lower not in _STOPWORDS and w_lower not in seen:
            seen.add(w_lower)
            result.append(w)
    return result


def _extract_proper_nouns(text: str) -> list[str]:
    if not text:
        return []
    matches = re.findall(
        r'(?:^|[.!?;,:]\s{0,5})([A-Z][a-zÀ-ÿ]{2,}(?:\s[A-Z][a-zÀ-ÿ]{2,})?)',
        text
    )
    mid_caps = re.findall(r'\b([A-Z][a-zÀ-ÿ]{3,})\b', text)
    all_nouns = [m.strip() for m in matches if m.strip()]
    for w in mid_caps:
        if w not in all_nouns:
            all_nouns.append(w)
    return [n for n in all_nouns if n.lower() not in _STOPWORDS][:5]


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


def _filter_by_genre_year(
    candidates: list,
    genre: str,
    annee: str,
) -> list:
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