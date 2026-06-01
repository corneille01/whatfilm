# storage/cache.py
# Cache Redis à 3 clés complémentaires + fallback RAM si Redis indisponible
#
# Clé 1  url:{md5(url)}            → résultat complet   TTL 7 jours
# Clé 2  content:{sha256(texte)}   → tmdb_id            TTL 30 jours
# Clé 3  film:{tmdb_id}:{lang}     → résultat complet   TTL infini (pas d'expiry)
#
# Logique :
#   - Toute bonne reconnaissance (score ≥ 50) est stockée sous les 3 clés
#   - La clé 3 est universelle : Matrix sera toujours Matrix peu importe le lien
#   - La clé 2 permet de retrouver le tmdb_id depuis un nouveau transcript
#     et de servir la clé 3 directement sans refaire l'analyse
#   - Fallback RAM transparent si Redis est down (déploiement progressif)

import hashlib
import json
import os
import re
import time
from typing import Optional

# ── Connexion Redis (optionnelle) ─────────────────────────────────
_redis = None
_redis_available = False

def _connect_redis():
    global _redis, _redis_available
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        print("ℹ️  REDIS_URL absent → cache RAM uniquement", flush=True)
        return
    try:
        import redis
        _redis = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )
        _redis.ping()
        _redis_available = True
        print("✅ Redis connecté", flush=True)
    except Exception as e:
        print(f"⚠️  Redis indisponible → fallback RAM ({e})", flush=True)
        _redis_available = False

_connect_redis()

# ── Fallback RAM ──────────────────────────────────────────────────
_ram: dict = {}

EXPIRES_NEVER = float('inf')
TTL_URL       = 7 * 86400    # 7 jours
TTL_CONTENT   = 30 * 86400   # 30 jours
TTL_UNCERTAIN = 3600         # 1h

# ── Clés Redis ────────────────────────────────────────────────────
def _key_url(url: str) -> str:
    return "url:" + hashlib.md5(url.encode()).hexdigest()

def _key_film(tmdb_id, lang: str) -> str:
    return f"film:{tmdb_id}:{lang}"

def _key_content(transcript: str, ocr_text: str) -> Optional[str]:
    combined = (transcript or "") + " " + (ocr_text or "")
    normalized = re.sub(r"[^a-z0-9àâäéèêëïîôùûüç]", " ", combined.lower())
    words = sorted(set(normalized.split()))
    meaningful = [w for w in words if len(w) >= 4]
    if len(meaningful) < 5:
        return None
    return "content:" + hashlib.sha256(" ".join(meaningful).encode()).hexdigest()[:32]

# ── Redis helpers ─────────────────────────────────────────────────
def _rget(key: str) -> Optional[dict]:
    if not _redis_available:
        return None
    try:
        raw = _redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

def _rset(key: str, data: dict, ttl: Optional[int] = None) -> None:
    if not _redis_available:
        return
    try:
        raw = json.dumps(data, ensure_ascii=False)
        if ttl:
            _redis.setex(key, ttl, raw)
        else:
            _redis.set(key, raw)   # pas d'expiry → permanent
    except Exception as e:
        print(f"⚠️  Redis write error: {e}", flush=True)

# ── RAM helpers ───────────────────────────────────────────────────
def _ramget(key: str) -> Optional[dict]:
    entry = _ram.get(key)
    if not entry:
        return None
    if entry.get("expires") == EXPIRES_NEVER or time.time() < entry.get("expires", 0):
        return entry["data"]
    del _ram[key]
    return None

def _ramset(key: str, data: dict, ttl: Optional[int] = None) -> None:
    expires = EXPIRES_NEVER if not ttl else time.time() + ttl
    _ram[key] = {"data": data, "expires": expires}

# ── API publique ──────────────────────────────────────────────────

def get_cache(url: str) -> Optional[dict]:
    """Cherche par URL exacte."""
    key = _key_url(url)
    data = _rget(key) or _ramget(key)
    if data:
        print(f"✅ Cache URL hit", flush=True)
    return data

def get_cache_by_content(transcript: str, ocr_text: str,
                          lang: str = "fr") -> Optional[dict]:
    """
    Cherche par empreinte du transcript.
    Si trouvé → retourne le tmdb_id → cherche la clé film universelle.
    """
    content_key = _key_content(transcript, ocr_text)
    if not content_key:
        return None

    # La clé content stocke juste le tmdb_id (léger)
    tmdb_id = _rget(content_key) or _ramget(content_key)
    if not tmdb_id:
        return None

    # Chercher le résultat complet via la clé film universelle
    film_key = _key_film(tmdb_id, lang)
    data = _rget(film_key) or _ramget(film_key)
    if data:
        print(f"✅ Cache contenu hit → film:{tmdb_id}:{lang}", flush=True)
    return data

def get_cache_by_film(tmdb_id, lang: str) -> Optional[dict]:
    """
    Cherche directement par tmdb_id + langue.
    Appelé dans process_analysis AVANT l'appel TMDB/Gemini
    si on a déjà identifié le film.
    """
    key = _key_film(tmdb_id, lang)
    data = _rget(key) or _ramget(key)
    if data:
        print(f"✅ Cache film hit: {tmdb_id}:{lang}", flush=True)
    return data

def set_cache(url: str, data: dict,
              transcript: str = "", ocr_text: str = "") -> None:
    """
    Enregistre sous les 3 clés si résultat fiable (score ≥ 50).
    """
    confidence = data.get("confidence", 0)
    tmdb_id    = data.get("tmdb_id")
    lang       = data.get("lang", "fr")  # on stockera la langue dans le résultat

    # Clé 1 : URL (7 jours)
    _rset(_key_url(url), data, TTL_URL)
    _ramset(_key_url(url), data, TTL_URL)

    if confidence >= 50 and tmdb_id:
        # Clé 3 : film universel (permanent — pas d'expiry Redis)
        film_key = _key_film(tmdb_id, lang)
        _rset(film_key, data, ttl=None)   # None = pas d'expiry dans Redis
        _ramset(film_key, data, ttl=None)
        print(f"💾 Cache film permanent: {tmdb_id}:{lang}", flush=True)

        # Clé 2 : content → tmdb_id (30 jours)
        content_key = _key_content(transcript, ocr_text)
        if content_key:
            _rset(content_key, tmdb_id, TTL_CONTENT)
            _ramset(content_key, tmdb_id, TTL_CONTENT)
            print(f"💾 Cache contenu → {tmdb_id} (30j)", flush=True)

def cache_stats() -> dict:
    stats = {
        "redis": _redis_available,
        "ram_entries": len(_ram),
    }
    if _redis_available:
        try:
            info = _redis.info("memory")
            stats["redis_memory_mb"] = round(
                info.get("used_memory", 0) / 1024 / 1024, 2)
            stats["redis_keys"] = _redis.dbsize()
        except Exception:
            pass
    return stats

def purge_expired() -> int:
    """Purge uniquement le cache RAM (Redis gère ses TTL tout seul)."""
    now = time.time()
    expired = [k for k, v in _ram.items()
               if v.get("expires") != EXPIRES_NEVER
               and now >= v.get("expires", 0)]
    for k in expired:
        del _ram[k]
    if expired:
        print(f"🧹 RAM purgée: {len(expired)} entrées", flush=True)
    return len(expired)