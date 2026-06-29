"""
storage/university_client.py — Client HTTP pour l'API PHP universitaire.

Cette API expose deux familles d'endpoints, tous protégés par le header
X-Pelify-Key (cf. config.php côté PHP) :

  - /index.php?endpoint=cache       → cache clé-valeur persistant (MySQL)
  - /index.php?endpoint=embeddings  → embeddings texte/visuel + recherche
    par similarité cosine

Conçu pour être autonome et réutilisable : ce module ne remplace pas
automatiquement storage/cache_engine/, il fournit une interface HTTP
propre que le reste du code peut appeler explicitement (cache_manager.py,
extraction.py, ou un futur module embeddings_engine.py).

Résilience :
  - Retry + backoff exponentiel sur erreurs réseau/5xx (3 tentatives)
  - Timeout court (8s) pour ne jamais bloquer longtemps le pipeline
    principal si le serveur universitaire est lent ou indisponible
  - Toute fonction retourne None (ou une valeur par défaut sûre) en cas
    d'échec définitif, jamais d'exception qui remonterait casser
    l'appelant — exactement le même principe que _cache_get/_cache_set
    dans extraction.py (jamais bloquant).

Variables d'environnement attendues :
  PELIFY_API_URL    — ex: https://tonserveur.univ.fr/pelify-api/index.php
  PELIFY_API_SECRET — la même clé que PELIFY_API_SECRET dans config.php
"""

import os
import random
import asyncio
from typing import Any, Optional, List, Dict

import httpx

PELIFY_API_URL    = os.environ.get("PELIFY_API_URL", "")
PELIFY_API_SECRET = os.environ.get("PELIFY_API_SECRET", "")

_TIMEOUT       = 8.0
_MAX_RETRIES   = 3
_BASE_DELAY    = 0.5  # secondes


def _is_configured() -> bool:
    return bool(PELIFY_API_URL and PELIFY_API_SECRET)


async def _request(method: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> Optional[dict]:
    """
    Effectue une requête HTTP vers l'API PHP avec retry sur erreurs
    réseau et 5xx. Retourne le JSON décodé en cas de succès, None sinon.
    Ne lève jamais d'exception vers l'appelant.
    """
    if not _is_configured():
        print("⚠️ University API non configurée (PELIFY_API_URL/SECRET manquants)", flush=True)
        return None

    headers = {"X-Pelify-Key": PELIFY_API_SECRET}
    last_error: Optional[str] = None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for attempt in range(_MAX_RETRIES):
            try:
                if method == "GET":
                    resp = await client.get(PELIFY_API_URL, params=params, headers=headers)
                else:
                    resp = await client.post(PELIFY_API_URL, params=params, json=json_body, headers=headers)

                if resp.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.3)
                    print(f"⏳ University API {resp.status_code}, retry {attempt + 1}/{_MAX_RETRIES} dans {delay:.1f}s...", flush=True)
                    await asyncio.sleep(delay)
                    continue

                if resp.status_code == 401:
                    print("⚠️ University API: clé invalide (401) — vérifier PELIFY_API_SECRET", flush=True)
                    return None

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
                if e.response.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)
                    continue
                break
            except Exception as e:
                last_error = str(e)[:120]
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.3)
                    await asyncio.sleep(delay)
                    continue
                break

    print(f"⚠️ University API KO après {_MAX_RETRIES} tentatives: {last_error}", flush=True)
    return None


# ═══════════════════════════ CACHE ═══════════════════════════

async def university_cache_get(key: str) -> Optional[Any]:
    """
    Récupère une entrée du cache MySQL université.
    Retourne None si absente, expirée, ou en cas d'erreur réseau.
    """
    result = await _request("GET", params={"endpoint": "cache", "key": key})
    if result is None or not result.get("found"):
        return None
    return result.get("data")


async def university_cache_set(key: str, data: Any, ttl_seconds: Optional[int] = None) -> bool:
    """
    Insère ou remplace une entrée dans le cache MySQL université.
    ttl_seconds=None signifie "jamais expiré" côté PHP — à n'utiliser que
    pour des clés non-TMDB (locks, configs), jamais pour film:* ou title:*
    (cf. note de conformité TMDB dans le schéma SQL).
    Retourne True si l'écriture a réussi, False sinon (jamais d'exception).
    """
    body = {"action": "set", "key": key, "data": data}
    if ttl_seconds is not None:
        body["ttl_seconds"] = ttl_seconds

    result = await _request("POST", params={"endpoint": "cache"}, json_body=body)
    return result is not None and result.get("status") == "success"


async def university_cache_delete(key: str) -> bool:
    result = await _request(
        "POST",
        params={"endpoint": "cache"},
        json_body={"action": "delete", "key": key},
    )
    return result is not None and result.get("deleted", False)


async def university_cache_scan(pattern: str) -> List[str]:
    """
    Liste les clés correspondant à un motif SQL LIKE (ex: "film:%").
    Retourne une liste vide en cas d'erreur (jamais d'exception).
    """
    result = await _request("GET", params={"endpoint": "cache", "action": "scan", "pattern": pattern})
    if result is None:
        return []
    return result.get("keys", [])


# ═══════════════════════════ EMBEDDINGS ═══════════════════════════

async def university_insert_text_embedding(
    tmdb_id: int,
    embedding: List[float],
    media_type: str = "movie",
    lang: str = "fr",
    excerpt: Optional[str] = None,
) -> bool:
    body = {
        "action":     "insert_text",
        "tmdb_id":    tmdb_id,
        "media_type": media_type,
        "lang":       lang,
        "embedding":  embedding,
    }
    if excerpt:
        body["excerpt"] = excerpt[:500]

    result = await _request("POST", params={"endpoint": "embeddings"}, json_body=body)
    return result is not None and result.get("status") == "success"


async def university_insert_visual_embedding(
    tmdb_id: int,
    embedding: List[float],
    media_type: str = "movie",
    frame_index: int = 0,
    frame_hash: Optional[str] = None,
) -> bool:
    body = {
        "action":      "insert_visual",
        "tmdb_id":     tmdb_id,
        "media_type":  media_type,
        "frame_index": frame_index,
        "embedding":   embedding,
    }
    if frame_hash:
        body["frame_hash"] = frame_hash

    result = await _request("POST", params={"endpoint": "embeddings"}, json_body=body)
    return result is not None and result.get("status") == "success"


async def university_search_text_embeddings(
    embedding: List[float],
    top_k: int = 5,
    threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """
    Recherche les meilleurs matches par similarité cosine sur les embeddings
    texte. Retourne une liste de dicts {tmdb_id, media_type, lang, score}
    triés par score décroissant, filtrés par le seuil minimal.
    Retourne une liste vide en cas d'erreur (jamais d'exception) — le
    code appelant doit alors basculer sur le fallback LLM normal.
    """
    body = {"action": "search_text", "embedding": embedding, "top_k": top_k, "threshold": threshold}
    result = await _request("POST", params={"endpoint": "embeddings"}, json_body=body)
    if result is None:
        return []
    return result.get("matches", [])


async def university_search_visual_embeddings(
    embedding: List[float],
    top_k: int = 5,
    threshold: float = 0.90,
) -> List[Dict[str, Any]]:
    """
    Même principe que university_search_text_embeddings mais sur les
    embeddings visuels (CLIP). Le seuil par défaut est plus strict (0.90)
    car les faux positifs visuels sont plus dangereux : deux scènes
    différentes peuvent se ressembler visuellement sans être le même film.
    """
    body = {"action": "search_visual", "embedding": embedding, "top_k": top_k, "threshold": threshold}
    result = await _request("POST", params={"endpoint": "embeddings"}, json_body=body)
    if result is None:
        return []
    return result.get("matches", [])


async def university_log_match(
    query_type: str,
    similarity_score: float,
    threshold_used: float,
    accepted: bool,
    matched_tmdb_id: Optional[int] = None,
    fallback_to_llm: bool = False,
) -> None:
    """
    Journalise un match (accepté ou rejeté) pour calibration future du
    seuil de confiance. Ne retourne rien et n'échoue jamais bruyamment :
    c'est un log à but d'analyse, pas un chemin critique du pipeline.
    """
    if query_type not in ("text", "visual"):
        return

    body = {
        "action":           "log_match",
        "query_type":        query_type,
        "matched_tmdb_id":   matched_tmdb_id,
        "similarity_score":  similarity_score,
        "threshold_used":    threshold_used,
        "accepted":          accepted,
        "fallback_to_llm":   fallback_to_llm,
    }

    await _request("POST", params={"endpoint": "embeddings"}, json_body=body)


# ═══════════════════════════ DIAGNOSTIC ═══════════════════════════

async def university_health_check() -> bool:
    """
    Vérifie que l'API université répond correctement. Utile pour un
    endpoint /health côté Render ou un log de démarrage.
    """
    if not _is_configured():
        return False

    # Une clé qui n'existera jamais : on attend juste une réponse 200
    # avec found=false, pas une erreur — ça confirme que la connexion
    # PDO + l'authentification fonctionnent côté PHP.
    result = await _request("GET", params={"endpoint": "cache", "key": "__health_check__"})
    return result is not None and result.get("status") == "success"