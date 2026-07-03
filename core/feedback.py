"""
core/feedback.py — Collecte et auto-correction des signalements utilisateurs.

Aucune intervention manuelle : chaque signalement est soit appliqué
immédiatement (candidat déjà vu pendant l'analyse), soit mis en attente
de corroboration (2 IPs distinctes d'accord) avant application, jamais
validé à l'aveugle sur un seul avis isolé.

Généralisation sans embeddings : une correction validée est aussi indexée
par "signature" (acteurs + titre extraits par le LLM), stockée dans Redis
Upstash. Un autre extrait TikTok du même film, ayant le même acteur
reconnu, bénéficie directement de la correction — sans base vectorielle.
"""

import hashlib
from typing import Optional

from storage.cache_engine.cache_manager import cache_get, cache_set
from storage.cache import set_cache, delete_cache, cache_get_generic, cache_set_generic
from data.tmdb import get_movie_details, get_tv_details
from core.embeddings_engine import store_film_signature

CANDIDATES_SNAPSHOT_TTL = 24 * 3600     # candidats/extraction gardés 24h
PENDING_REPORT_TTL      = 48 * 3600     # fenêtre de corroboration
CORRECTION_TTL          = 90 * 24 * 3600  # correction généralisée 90 jours
MIN_INDEPENDENT_REPORTS = 2             # signalements distincts requis si non-candidat


# ════════════════════════════════════════════════════════════════
# SNAPSHOTS (posés à chaque analyse, servent à valider un futur signalement)
# ════════════════════════════════════════════════════════════════

def _candidates_key(content_hash: str) -> str:
    return f"snapshot_candidates:{content_hash}"

def _extraction_key(content_hash: str) -> str:
    return f"snapshot_extraction:{content_hash}"


def save_candidates_snapshot(content_hash: str, candidates: list) -> None:
    ids = list({c["id"] for c in candidates if c.get("id")})
    cache_set(_candidates_key(content_hash), ids, ttl=CANDIDATES_SNAPSHOT_TTL)


def save_extraction_snapshot(content_hash: str, extraction: dict) -> None:
    cache_set_generic(_extraction_key(content_hash), extraction, ttl=CANDIDATES_SNAPSHOT_TTL)


# ════════════════════════════════════════════════════════════════
# SIGNATURE ACTEURS/TITRE (généralisation sans embeddings)
# ════════════════════════════════════════════════════════════════

def _signature(extraction: dict) -> Optional[str]:
    """
    Empreinte légère basée sur acteurs + titre certain extraits par le LLM.
    Deux extraits différents du même film donnent souvent la même signature
    (mêmes acteurs reconnus), sans avoir besoin d'embeddings audio/visuels.
    """
    acteurs = sorted(a.lower().strip() for a in extraction.get("acteurs", []) or [])
    titres_certains = sorted(
        str(t).lower().strip() for t in extraction.get("titres_possibles", []) or []
        if t and not str(t).startswith("?")
    )
    if not acteurs and not titres_certains:
        return None
    raw = "|".join(acteurs) + "::" + "|".join(titres_certains)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def get_correction_for_extraction(extraction: dict) -> Optional[dict]:
    """
    Appelé au début du pipeline : si ce même acteur/titre a déjà été
    corrigé par un utilisateur, on récupère directement le bon film,
    sans repasser par le LLM/cascade.
    """
    sig = _signature(extraction)
    if not sig:
        return None
    return cache_get_generic(f"correction_sig:{sig}")


# ════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE SIGNALEMENT
# ════════════════════════════════════════════════════════════════

async def submit_feedback(
    url: str,
    content_hash: str,
    transcript: str,
    ocr_text: str,
    reported_wrong_id: Optional[int],
    corrected_tmdb_id: int,
    corrected_media_type: str,
    ip: str,
    lang: str = "fr",
) -> dict:
    """
    Retourne toujours un statut clair : "applied" (corrigé immédiatement)
    ou "pending" (en attente de corroboration).
    """
    known_ids = cache_get(_candidates_key(content_hash)) or []
    was_known_candidate = corrected_tmdb_id in known_ids

    if was_known_candidate:
        await _apply_correction(
            url, content_hash, transcript, ocr_text,
            corrected_tmdb_id, corrected_media_type, lang,
        )
        return {"status": "applied", "reason": "candidat_deja_vu"}

    # ── Voie lente : corroboration entre signalements indépendants ──
    pending_key = f"pending_report:{content_hash}:{corrected_tmdb_id}"
    reporters   = cache_get(pending_key) or []
    if ip not in reporters:
        reporters.append(ip)
        cache_set(pending_key, reporters, ttl=PENDING_REPORT_TTL)

    if len(reporters) >= MIN_INDEPENDENT_REPORTS:
        await _apply_correction(
            url, content_hash, transcript, ocr_text,
            corrected_tmdb_id, corrected_media_type, lang,
        )
        cache_set(pending_key, [], ttl=1)
        return {"status": "applied", "reason": "corroboration_atteinte"}

    return {
        "status":         "pending",
        "reports_so_far":  len(reporters),
        "reports_needed":  MIN_INDEPENDENT_REPORTS,
    }


# ════════════════════════════════════════════════════════════════
# APPLICATION DE LA CORRECTION
# ════════════════════════════════════════════════════════════════

async def _apply_correction(
    url: str,
    content_hash: str,
    transcript: str,
    ocr_text: str,
    tmdb_id: int,
    media_type: str,
    lang: str,
) -> None:
    """
    1. Corrige le cache pour CETTE URL (effet immédiat, exact).
    2. Indexe par signature acteurs/titre (effet généralisé, sans embeddings).
    3. Nourrit les embeddings si un jour réactivés (no-op sinon).
    """
    delete_cache(url)

    try:
        details = (
            await get_tv_details(tmdb_id, lang)
            if media_type == "tv"
            else await get_movie_details(tmdb_id, lang)
        )
    except Exception as e:
        print(f"⚠️ Feedback: TMDB KO pour tmdb_id={tmdb_id}: {e}", flush=True)
        return

    final = {
        "status":     "success",
        "media_type": media_type,
        "title":      details.get("title") or details.get("name") or "Inconnu",
        "confidence": 95,
        "synopsis":   details.get("overview", ""),
        "image":      (f"https://image.tmdb.org/t/p/w500{details['poster_path']}"
                       if details.get("poster_path") else ""),
        "tmdb_id":    tmdb_id,
        "lang":       lang,
        "genres":     [g["name"] for g in details.get("genres", [])],
        "year":       (details.get("release_date") or details.get("first_air_date") or "")[:4],
        "is_series":  media_type == "tv",
    }
    set_cache(url, final, transcript=transcript or "", ocr_text=ocr_text or "")

    # ── Généralisation via signature acteurs/titre (sans embeddings) ──
    extraction_snapshot = cache_get_generic(_extraction_key(content_hash))
    if extraction_snapshot:
        sig = _signature(extraction_snapshot)
        if sig:
            cache_set_generic(
                f"correction_sig:{sig}",
                {"tmdb_id": tmdb_id, "media_type": media_type, "confidence": 90},
                ttl=CORRECTION_TTL,
            )
            print(f"🔁 Correction généralisée via signature: {sig}", flush=True)

    # ── Embeddings (no-op tant que EMBEDDINGS_ENABLED=false) ──
    await store_film_signature(
        tmdb_id=tmdb_id,
        confidence=95,
        media_type=media_type,
        lang=lang,
        transcript=transcript or "",
        ocr_text=ocr_text or "",
        frame_paths=[],
    )
    print(f"✅ Correction appliquée automatiquement — tmdb_id={tmdb_id}", flush=True)