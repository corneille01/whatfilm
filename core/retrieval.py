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

Fixes v4 :
  - build_candidates_from_actors : credits[:30] au lieu de [:15]
    → évite de rater des séries TV moins populaires (ex: The Shield)
  - build_candidates_from_actors : filtre genre/année désactivé pour les
    genres génériques (film-action, drame…) qui excluent les séries TV
  - _GENERIC_GENRES : liste des genres trop larges pour filtrer
  - Pas d'autres changements vs v3
"""

import re
import asyncio

from data.tmdb import search_person, get_person_credits, search_multi_lang


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

# Genres trop génériques pour filtrer les candidats acteurs :
# ils excluent les séries TV et les films de genres voisins.
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
# BUILD CASCADE QUERIES
# ════════════════════════════════════════════════════════════════

async def build_cascade_queries(extraction: dict) -> list[str]:
    """
    Génère une liste de requêtes par ordre de précision décroissante.

      - Niveau 1   : titres certains
      - Niveau 1b  : titres incertains mais précis (ex: "?Love, Death & Robots")
      - Niveau 2   : acteurs connus
      - Niveau 3   : personnages
      - Niveau 4   : combinaisons indices_visuels + objets (FR + EN)
      - Niveau 5   : mots-clés description_courte (FR)
      - Niveau 5b  : termes EN extraits de description_courte
      - Niveau 5c  : termes JP si contenu japonais détecté
      - Niveau 6   : titres incertains vagues (descriptions)
      - Niveau 7   : spécifiques au type de média (anime, documentaire)
      - Niveau 8   : indices seuls (dernier recours)
    """
    titres_certains          = []
    titres_incertains_precis = []   # titres ? qui ressemblent à de vrais titres
    titres_incertains        = []   # titres ? vagues (descriptions)

    for t in extraction.get("titres_possibles", []):
        t = str(t).strip()
        if not t:
            continue
        if t.startswith("?"):
            titre_clean = t[1:].strip()
            if not titre_clean:
                continue
            # Titre précis = majuscule interne, ponctuation spéciale, chiffre,
            # ou plusieurs mots dont au moins un commence par une majuscule
            is_precise = (
                re.search(r'(?<=[a-z])[A-Z]', titre_clean)        # camelCase interne
                or re.search(r'[,&:\d\-]', titre_clean)            # ponctuation/chiffre
                or (
                    len(titre_clean.split()) >= 2
                    and any(
                        w[0].isupper()
                        for w in titre_clean.split()[1:]
                        if w
                    )
                )
                or len(titre_clean.split()) == 1 and titre_clean[0].isupper()
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

    queries = []

    # ── Niveau 1 : titres certains ───────────────────────────────
    for titre in titres_certains:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")
        if annee:
            queries.append(f"{titre} {annee}")

    # ── Niveau 1b : titres incertains précis ─────────────────────
    # Ex: "?Love, Death & Robots", "?Automated Customer Service"
    # Cherchés AVANT les indices visuels car très probablement corrects.
    for titre in titres_incertains_precis:
        queries.append(titre)
        if annee:
            queries.append(f"{titre} {annee}")
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 2 : acteurs ───────────────────────────────────────
    if acteurs:
        queries.append(f"{acteurs[0]} {genre} {annee}".strip())
        queries.append(acteurs[0])
    if len(acteurs) >= 2:
        queries.append(f"{acteurs[0]} {acteurs[1]}")

    # ── Niveau 3 : personnages ───────────────────────────────────
    for perso in personnages[:2]:
        queries.append(f"{perso} {genre}".strip())

    # ── Niveau 4 : combinaisons indices + objets (FR + EN) ───────
    all_clues = [o for o in objets if o] + [i for i in indices if i]

    all_clues_en = []
    seen_en_clues: set[str] = set()
    for c in all_clues:
        translated = _translate_clue(c)
        if translated and translated not in seen_en_clues:
            seen_en_clues.add(translated)
            all_clues_en.append(translated)

    if len(all_clues) >= 2:
        for i in range(min(3, len(all_clues) - 1)):
            pair = f"{all_clues[i]} {all_clues[i+1]}"
            queries.append(pair)
            if genre:
                queries.append(f"{pair} {genre}")
            if annee:
                queries.append(f"{pair} {annee}")

    if len(all_clues) >= 3:
        triple = f"{all_clues[0]} {all_clues[1]} {all_clues[2]}"
        queries.append(triple)
        if genre:
            queries.append(f"{triple} {genre}")

    if len(all_clues_en) >= 2:
        for i in range(min(2, len(all_clues_en) - 1)):
            pair_en = f"{all_clues_en[i]} {all_clues_en[i+1]}"
            queries.append(pair_en)
            if genre_en:
                queries.append(f"{pair_en} {genre_en}")

    for clue_en in all_clues_en[:3]:
        queries.append(clue_en)

    # ── Niveau 5 : mots-clés description_courte (FR) ─────────────
    if description:
        keywords = _extract_keywords(description)
        if len(keywords) >= 3:
            queries.append(" ".join(keywords[:4]))
            if genre:
                queries.append(f"{' '.join(keywords[:3])} {genre}")
            if annee:
                queries.append(f"{' '.join(keywords[:3])} {annee}")
        proper_nouns = _extract_proper_nouns(description)
        for noun in proper_nouns[:2]:
            queries.append(noun)
            if genre:
                queries.append(f"{noun} {genre}")

    # ── Niveau 5b : termes EN depuis description FR ───────────────
    if description:
        desc_en_terms = _translate_text(description)
        if desc_en_terms:
            queries.append(" ".join(desc_en_terms[:3]))
            if genre_en:
                queries.append(f"{' '.join(desc_en_terms[:2])} {genre_en}")
            if annee:
                queries.append(f"{' '.join(desc_en_terms[:2])} {annee}")

    # ── Niveau 5c : requêtes japonaises si contenu JP détecté ─────
    if _is_japanese_content(all_clues, description, indices):
        jp_terms = _get_jp_terms(all_clues, description, indices)
        if jp_terms:
            print(f"🇯🇵 Contenu japonais détecté → requêtes JP: {jp_terms[:3]}", flush=True)
            if len(jp_terms) >= 2:
                queries.append(f"{jp_terms[0]} {jp_terms[1]}")
            queries.append(jp_terms[0])
            if annee:
                queries.append(f"{jp_terms[0]} {annee}")
            if all_clues_en:
                queries.append(f"{all_clues_en[0]} japanese")
                if genre_en:
                    queries.append(f"japanese {genre_en} {annee}".strip())

    # ── Niveau 6 : titres incertains vagues ──────────────────────
    for titre in titres_incertains:
        queries.append(titre)
        if acteurs:
            queries.append(f"{titre} {acteurs[0]}")

    # ── Niveau 7 : spécifiques au type de média ──────────────────
    if genre in ("anime", "serie-animation", "serie-animée"):
        for titre in (titres_certains + titres_incertains_precis + titres_incertains)[:2]:
            queries.append(f"{titre} anime")
        for perso in personnages[:1]:
            queries.append(f"{perso} anime")
        for clue_en in all_clues_en[:2]:
            queries.append(f"{clue_en} anime")

    if "document" in genre:
        for titre in titres_certains[:2]:
            queries.append(f"{titre} documentary")
        mots_doc = [
            m for m in re.findall(r"\b\w{5,}\b", description)
            if m.lower() not in _STOPWORDS
        ]
        if mots_doc:
            queries.append(f"{' '.join(mots_doc[:3])} documentary")

    # ── Niveau 8 : indices seuls (dernier recours) ───────────────
    for clue in all_clues[:3]:
        if len(clue) > 8:
            queries.append(clue)

    # ── Dédoublonnage ────────────────────────────────────────────
    seen   = set()
    result = []
    for q in queries:
        q = q.strip()
        if q and q not in seen and len(q) > 2:
            seen.add(q)
            result.append(q)

    print(f"🔍 Requêtes cascade ({len(result)}): {result[:6]}", flush=True)
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

    seen_ids:   set  = set()
    candidates: list = []

    for query in queries:
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
                candidates.append(item)
                added += 1

        if added > 0:
            print(
                f"  ↳ '{query}' → +{added} candidats "
                f"(total={len(candidates)})",
                flush=True
            )

        if query in titres_certains and len(candidates) >= 3:
            print(f"⚡ Early stop : titre certain '{query}' trouvé", flush=True)
            break

    candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    print(
        f"📋 Cascade terminée → {len(candidates)} candidats uniques",
        flush=True
    )
    return candidates[:max_candidates]


# ════════════════════════════════════════════════════════════════
# BUILD CANDIDATES FROM ACTORS
# ════════════════════════════════════════════════════════════════

async def build_candidates_from_actors(
    extraction: dict,
    lang: str = "fr",
) -> list:
    """
    Construit des candidats TMDB à partir des acteurs reconnus.

    Fix v4 :
    - credits[:30] au lieu de [:15] → évite de rater les séries moins populaires
    - filtre genre/année désactivé pour les genres génériques (_GENERIC_GENRES)
      → un genre comme "film-action" ne doit pas exclure The Shield (série)
    """
    acteurs = extraction.get("acteurs", []) or []
    if not acteurs:
        return []

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

    if not all_credits:
        return []

    if len(all_credits) >= 2:
        ids_first  = {c["id"] for c in all_credits[0]}
        common_ids = ids_first
        for credits in all_credits[1:]:
            common_ids &= {c["id"] for c in credits}
        if common_ids:
            candidates = [c for c in all_credits[0] if c["id"] in common_ids]
            candidates = sorted(
                candidates,
                key=lambda x: x.get("popularity", 0),
                reverse=True,
            )
            print(
                f"✅ Intersection acteurs: {len(candidates)} films communs",
                flush=True
            )
            return candidates[:20]
        print("⚠️ Aucune intersection acteurs → union top films", flush=True)

    seen_ids: set  = set()
    merged:   list = []
    for credits in all_credits:
        # Fix v4 : passer les 30 premiers crédits au lieu de 15
        # Les séries TV ont souvent une popularité plus faible que les films
        # et tombaient hors du top 15 (ex: The Shield de Michael Jai White)
        for c in credits[:30]:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                merged.append(c)

    merged = sorted(merged, key=lambda x: x.get("popularity", 0), reverse=True)

    genre = (extraction.get("genre_apparent") or "").lower()
    annee = str(extraction.get("annee_estimee") or "")

    # Fix v4 : ne pas filtrer si le genre est trop générique.
    # "film-action" exclut les séries ; "film-horreur" ou "anime" sont assez
    # spécifiques pour filtrer sans risque.
    genre_is_generic = genre in _GENERIC_GENRES or not genre
    if (genre or annee) and not genre_is_generic:
        filtered = _filter_by_genre_year(merged, genre, annee)
        if len(filtered) >= 3:
            print(
                f"🔍 Filtre genre/année appliqué : {len(merged)} → {len(filtered)} candidats",
                flush=True
            )
            merged = filtered
    elif genre_is_generic and (genre or annee):
        print(
            f"ℹ️  Genre '{genre}' trop générique → filtre désactivé "
            f"(évite d'exclure les séries TV)",
            flush=True
        )

    for c in merged:
        if "media_type" not in c:
            c["media_type"] = "tv" if "first_air_date" in c else "movie"

    print(f"✅ Candidats via acteurs: {len(merged[:20])}", flush=True)
    return merged[:20]


# ════════════════════════════════════════════════════════════════
# HELPERS PRIVÉS
# ════════════════════════════════════════════════════════════════

_STOPWORDS = {
    # Français
    "dans", "avec", "pour", "qui", "que", "les", "des", "une", "est",
    "sont", "cette", "leur", "plus", "tout", "mais", "dont", "elle",
    "lui", "ils", "elles", "nous", "vous", "très", "bien", "même",
    "aussi", "comme", "quand", "alors", "après", "avant", "jusqu",
    "entre", "contre", "sans", "sous", "sur", "par", "depuis",
    # Anglais
    "when", "what", "that", "this", "with", "from", "have", "they",
    "which", "been", "were", "their", "there", "about", "would",
    "could", "should", "other", "into", "than", "then", "some",
    # Espagnol / Allemand / Portugais
    "sehr", "wird", "eine", "auch", "oder", "para", "esto", "como",
    "donde", "tiene", "pero", "porque", "uma", "isso", "este",
    # Mots trop génériques pour une recherche film
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
    """Filtre les candidats par genre TMDB et/ou année (±3 ans de tolérance)."""
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