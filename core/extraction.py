"""
core/extraction.py — Extraction multimodale simplifiée.

Cascade :
  0. Regex        → si titre trouvé directement (0 API call)
  1. Gemini vision → transcript + OCR + 6 frames (toujours)
  2. Fallback     → retour minimal
"""

import re
import json
import os
import base64
import httpx

from core.prompts import EXTRACTION_PROMPT

# ── Clés API ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
print(f"🔑 GEMINI_API_KEY présente: {bool(GEMINI_API_KEY)}", flush=True)

GEMINI_URLS = [
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
]

TRANSCRIPT_THRESHOLD = 80


# # ════════════════════════════════════════════════════════════════
# # NIVEAU 0 — Regex avancé (0 API call)
# # ════════════════════════════════════════════════════════════════

# # Années valides pour films/séries
# _YEAR_PATTERN = re.compile(r"\b(19[3-9]\d|20[0-3]\d)\b")

# # Titres entre guillemets (toutes variantes internationales)
# _QUOTED_TITLE = re.compile(
#     r'[«»""„‟❝❞〈〉《》【】『』「」\u201c\u201d\u201e\u2039\u203a]'
#     r'([^«»""„‟❝❞〈〉《》【】『』「」\u201c\u201d\u201e\u2039\u203a]{2,80})'
#     r'[«»""„‟❝❞〈〉《》【】『』「」\u201c\u201d\u201e\u2039\u203a]'
# )

# # Préfixes d'acteurs multilingues
# _ACTOR_PREFIXES = re.compile(
#     r"(?:avec|starring|mit|con|com|featuring|feat\.?|avec les acteurs|"
#     r"interprété par|joué par|played by|avec en vedette)\s+"
#     r"([A-ZÀ-ÿ\u00C0-\u024F][a-zà-ÿ\u00C0-\u024F]+"
#     r"(?:\s+[A-ZÀ-ÿ\u00C0-\u024F][a-zà-ÿ\u00C0-\u024F]+){0,3})",
#     re.IGNORECASE
# )

# # Mots-clés de présentation de film
# _FILM_INTRO = re.compile(
#     r"(?:film|movie|série|series|anime|documentaire|documentary|"
#     r"saison|season|épisode|episode|extrait de|tiré de|based on|"
#     r"bande.?annonce|trailer|teaser|clip de)\s*[:\-]?\s*"
#     r"([A-ZÀ-ÿ\u00C0-\u024F][^\n\.!?]{2,60})",
#     re.IGNORECASE
# )

# # Hashtags (souvent contiennent le titre)
# _HASHTAG = re.compile(r"#([A-ZÀ-ÿa-z\u00C0-\u024F][A-ZÀ-ÿa-z0-9\u00C0-\u024F]{2,40})")

# # Titres en MAJUSCULES (affiches, génériques)
# _CAPS_TITLE = re.compile(
#     r"\b([A-ZÀ-ÿ\u00C0-\u024F]{2,}(?:\s+[A-ZÀ-ÿ\u00C0-\u024F]{2,}){0,5})\b"
# )

# # Patterns "Le film X", "La série X", "Watch X", "Regardez X"
# _WATCH_PATTERN = re.compile(
#     r"(?:regardez?|watch|voir|see|découvrez?|discover)\s+"
#     r"(?:le film|la série|the movie|the series|l'anime)?\s*"
#     r"[«»\"']?([A-ZÀ-ÿ\u00C0-\u024F][^\n\.!?«»\"']{2,50})[«»\"']?",
#     re.IGNORECASE
# )

# # Patterns "disponible sur", "en salle", "now playing"
# _RELEASE_PATTERN = re.compile(
#     r"([A-ZÀ-ÿ\u00C0-\u024F][^\n\.!?]{2,50})\s+"
#     r"(?:disponible|en salle|au cinéma|now playing|now streaming|"
#     r"coming soon|bientôt|sortie le|release)",
#     re.IGNORECASE
# )

# # Noms propres connus (personnages récurrents → titre)
# _CHARACTER_PATTERN = re.compile(
#     r"(?:je suis|I am|I\'m|c\'est|it\'s|voici|here\'s)\s+"
#     r"([A-ZÀ-ÿ\u00C0-\u024F][a-zà-ÿ\u00C0-\u024F]+"
#     r"(?:\s+[A-ZÀ-ÿ\u00C0-\u024F][a-zà-ÿ\u00C0-\u024F]+)?)",
#     re.IGNORECASE
# )

# # Mots à ignorer dans les titres caps (trop génériques)
# _STOPWORDS = {
#     "THE", "LES", "DES", "UNE", "EST", "QUE", "QUI", "PAR", "SUR",
#     "AVEC", "POUR", "DANS", "AND", "THE", "FOR", "WITH", "FROM",
#     "THIS", "THAT", "SONT", "MAIS", "PLUS", "BIEN", "TOUT", "TRÈS",
#     "VOUS", "NOUS", "ILS", "ELLE", "LEUR", "MON", "TON", "SON",
# }


# def _score_titre(titre: str) -> int:
#     """Score de qualité d'un titre candidat (plus haut = meilleur)."""
#     score = 0
#     mots = titre.strip().split()

#     if not mots:
#         return 0

#     # Longueur optimale 1-6 mots
#     if 1 <= len(mots) <= 6:
#         score += 10
#     elif len(mots) > 8:
#         score -= 5

#     # Commence par une majuscule
#     if mots[0][0].isupper():
#         score += 5

#     # Pas trop de stopwords
#     stopwords_count = sum(1 for m in mots if m.upper() in _STOPWORDS)
#     score -= stopwords_count * 3

#     # Contient des chiffres (séries souvent : "The 100", "9-1-1")
#     if any(c.isdigit() for c in titre):
#         score += 2

#     # Trop court ou trop long
#     if len(titre) < 3:
#         score -= 10
#     if len(titre) > 60:
#         score -= 5

#     return score


# def _regex_extract(ocr_text: str, transcript: str) -> dict | None:
#     combined = f"{transcript} {ocr_text}".strip()
#     if len(combined) < TRANSCRIPT_THRESHOLD:
#         return None

#     years   = _YEAR_PATTERN.findall(combined)
#     quotes  = _QUOTED_TITLE.findall(combined)
#     actors  = _ACTOR_PREFIXES.findall(combined)
#     intros  = _FILM_INTRO.findall(combined)
#     hashtags = [h for h in _HASHTAG.findall(combined) if len(h) > 3]
#     watch   = _WATCH_PATTERN.findall(combined)
#     release = _RELEASE_PATTERN.findall(combined)
#     characters = _CHARACTER_PATTERN.findall(combined)

#     # Titres en caps depuis OCR uniquement
#     caps_raw = _CAPS_TITLE.findall(ocr_text) if ocr_text else []
#     caps = [
#         c.strip() for c in caps_raw
#         if len(c.strip()) > 3
#         and c.strip().upper() not in _STOPWORDS
#         and not all(w.upper() in _STOPWORDS for w in c.strip().split())
#     ]
    

#     # Fusion et déduplication avec scoring
#     candidats_bruts = quotes + intros + watch + release + hashtags + caps
#     candidats_bruts = [c.strip() for c in candidats_bruts if c and len(c.strip()) >= 2]
#     candidats_bruts = quotes + intros + watch + release + hashtags + caps + characters

#     # Déduplication insensible à la casse
#     seen = set()
#     candidats = []
#     for c in candidats_bruts:
#         key = c.lower().strip()
#         if key not in seen:
#             seen.add(key)
#             candidats.append(c)

#     # Tri par score
#     candidats_scores = sorted(
#         candidats,
#         key=lambda t: _score_titre(t),
#         reverse=True
#     )
#     titres_possibles = candidats_scores[:5]

#     if not titres_possibles and not actors and not years:
#         return None

#     print(
#         f"✅ Extraction regex — titres: {titres_possibles[:2]}, "
#         f"acteurs: {actors[:2]}, années: {years[:1]}",
#         flush=True
#     )
#     return {
#         "titres_possibles":   titres_possibles,
#         "acteurs":            actors[:4],
#         "personnages":        [],
#         "objets_importants":  [],
#         "description_courte": combined[:300],
#         "genre_apparent":     "",
#         "annee_estimee":      years[0] if years else None,
#         "langue_originale":   "",
#         "source":             "regex",
#     }


# # ════════════════════════════════════════════════════════════════
# # UTILITAIRES
# # ════════════════════════════════════════════════════════════════
# def _clean_json_fences(text: str) -> str:
#     if "```" in text:
#         text = text.split("```")[1]
#         if text.startswith("json"):
#             text = text[4:]
#     return text.strip()


# def _minimal_fallback(source: str) -> dict:
#     return {
#         "titres_possibles":   [],
#         "acteurs":            [],
#         "personnages":        [],
#         "objets_importants":  [],
#         "description_courte": "",
#         "genre_apparent":     "",
#         "annee_estimee":      None,
#         "langue_originale":   "",
#         "source":             source,
#     }


# ════════════════════════════════════════════════════════════════
# NIVEAU 1 — Gemini vision (frames + transcript + OCR)
# ════════════════════════════════════════════════════════════════
def _encode_image(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None


async def _extract_gemini_vision(frames: list, prompt: str) -> dict | None:
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY manquante → skip vision", flush=True)
        return None

    parts = []
    for fp in frames[:6]:  # toutes les 6 frames
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            b64 = _encode_image(fp)
            if b64:
                parts.append({
                    "inline_data": {"mime_type": "image/jpeg", "data": b64}
                })

    if not parts:
        print("⚠️ Aucune frame valide pour Gemini", flush=True)

    parts.append({"text": prompt})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        }
    }

    for url in GEMINI_URLS:
        model_name = url.split("/models/")[1].split(":")[0]
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{url}?key={GEMINI_API_KEY}", json=payload
                )
                resp.raise_for_status()

            text = (
                resp.json()
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()

            if not text:
                continue

            text = _clean_json_fences(text)
            data = json.loads(text)
            data["source"] = "gemini_vision"
            print(f"✅ Gemini vision OK ({model_name}, {len(text)} chars)", flush=True)
            print(f"🔍 EXTRACTION: titres={data.get('titres_possibles')}, acteurs={data.get('acteurs')}, desc={str(data.get('description_courte',''))[:80]}", flush=True)
            return data

        except json.JSONDecodeError:
            result = _minimal_fallback("gemini_partial")
            result["description_courte"] = text[:300] if "text" in locals() else ""
            return result
        except Exception as e:
            print(f"⚠️ Gemini KO ({model_name}): {str(e)[:120]}", flush=True)
            continue

    return None


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ════════════════════════════════════════════════════════════════
async def multimodal_extract(frames, ocr_text, transcript):
    ocr_text   = (ocr_text   or "").strip()
    transcript = (transcript or "").strip()

    prompt = EXTRACTION_PROMPT.format(
        ocr_text=ocr_text,
        transcript=transcript
    )

    

    # ── 1. Gemini vision (toujours) ───────────────────────────────
    print("🔍 Gemini vision...", flush=True)
    result = await _extract_gemini_vision(frames, prompt)
    if result:
        return result

    # ── 2. Fallback minimal ───────────────────────────────────────
    print("⚠️ Extraction échouée → retour minimal", flush=True)
    combined = f"{transcript} {ocr_text}".strip()
    result = _minimal_fallback("fallback")
    result["description_courte"] = combined[:300]
    return result