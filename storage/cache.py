# storage/cache.py  ← remplace ENTIÈREMENT l'ancien fichier
import hashlib
import json
import os
import re
import time
from typing import Optional

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
            redis_url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2, retry_on_timeout=False,
        )
        _redis.ping()
        _redis_available = True
        print("✅ Redis connecté", flush=True)
    except Exception as e:
        print(f"⚠️  Redis indisponible → fallback RAM ({e})", flush=True)
        _redis_available = False

_connect_redis()

_ram: dict = {}
EXPIRES_NEVER = float('inf')
TTL_URL       = 7 * 86400
TTL_CONTENT   = 30 * 86400
TTL_UNCERTAIN = 3600

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

def _key_title(title: str) -> Optional[str]:
    normalized = re.sub(r"[^a-z0-9]", "", title.lower().strip())
    if len(normalized) < 3:
        return None
    return "title:" + normalized

def _rget(key: str):
    if not _redis_available:
        return None
    try:
        raw = _redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

def _rset(key: str, data, ttl: Optional[int] = None) -> None:
    if not _redis_available:
        return
    try:
        raw = json.dumps(data, ensure_ascii=False)
        if ttl is not None:
            _redis.setex(key, ttl, raw)
        else:
            _redis.set(key, raw)
    except Exception as e:
        print(f"⚠️  Redis write error: {e}", flush=True)

def _ramget(key: str):
    entry = _ram.get(key)
    if not entry:
        return None
    if entry.get("expires") == EXPIRES_NEVER or time.time() < entry.get("expires", 0):
        return entry["data"]
    del _ram[key]
    return None

def _ramset(key: str, data, ttl: Optional[int] = None) -> None:
    expires = EXPIRES_NEVER if ttl is None else time.time() + ttl
    _ram[key] = {"data": data, "expires": expires}

def get_cache(url: str) -> Optional[dict]:
    key = _key_url(url)
    data = _rget(key) or _ramget(key)
    if data:
        print(f"✅ Cache URL hit", flush=True)
    return data

def get_cache_by_content(transcript: str, ocr_text: str, lang: str = "fr") -> Optional[dict]:
    content_key = _key_content(transcript, ocr_text)
    if not content_key:
        return None
    tmdb_id = _rget(content_key) or _ramget(content_key)
    if not tmdb_id:
        return None
    return get_cache_by_film(tmdb_id, lang)

def get_cache_by_film(tmdb_id, lang: str) -> Optional[dict]:
    key = _key_film(tmdb_id, lang)
    data = _rget(key) or _ramget(key)
    if data:
        print(f"✅ Cache film hit: {tmdb_id}:{lang}", flush=True)
    return data

def get_cache_by_title(title: str, lang: str) -> Optional[dict]:
    key = _key_title(title)
    if not key:
        return None
    tmdb_id = _rget(key) or _ramget(key)
    if not tmdb_id:
        return None
    return get_cache_by_film(tmdb_id, lang)

def set_cache(url: str, data: dict, transcript: str = "", ocr_text: str = "") -> None:
    confidence     = data.get("confidence", 0)
    tmdb_id        = data.get("tmdb_id")
    lang           = data.get("lang", "fr")
    title          = data.get("title", "")
    original_title = data.get("original_title", "")

    _rset(_key_url(url), data, TTL_URL)
    _ramset(_key_url(url), data, TTL_URL)

    if confidence >= 50 and tmdb_id:
        film_key = _key_film(tmdb_id, lang)
        _rset(film_key, data, ttl=None)
        _ramset(film_key, data, ttl=None)
        print(f"💾 Cache film permanent: {tmdb_id}:{lang}", flush=True)

        content_key = _key_content(transcript, ocr_text)
        if content_key:
            _rset(content_key, tmdb_id, TTL_CONTENT)
            _ramset(content_key, tmdb_id, TTL_CONTENT)

        if title:
            set_cache_title(title, tmdb_id)
        if original_title and original_title != title:
            set_cache_title(original_title, tmdb_id)

def set_cache_title(title: str, tmdb_id: int) -> None:
    key = _key_title(title)
    if not key:
        return
    _rset(key, tmdb_id, ttl=None)
    _ramset(key, tmdb_id, ttl=None)

def cache_stats() -> dict:
    stats = {"redis": _redis_available, "ram_entries": len(_ram)}
    if _redis_available:
        try:
            info = _redis.info("memory")
            stats["redis_memory_mb"] = round(info.get("used_memory", 0) / 1024 / 1024, 2)
            stats["redis_keys"] = _redis.dbsize()
        except Exception:
            pass
    return stats

def purge_expired() -> int:
    now = time.time()
    expired = [k for k, v in _ram.items()
               if v.get("expires") != EXPIRES_NEVER and now >= v.get("expires", 0)]
    for k in expired:
        del _ram[k]
    if expired:
        print(f"🧹 RAM purgée: {len(expired)} entrées", flush=True)
    return len(expired)

def purge_by_code(code: str) -> int:
    """Purge RAM + Redis : toutes les entrées url:* dont data.code == code."""
    count = 0
    # RAM
    to_delete = [
        k for k, v in _ram.items()
        if isinstance(v.get("data"), dict)
        and (v["data"].get("code") == code or v["data"].get("status") == code)
    ]
    for k in to_delete:
        del _ram[k]
        count += 1
    # Redis (scan url:* uniquement)
    if _redis_available:
        try:
            for key in _redis.scan_iter("url:*", count=200):
                raw = _redis.get(key)
                if raw:
                    try:
                        data = json.loads(raw)
                        if isinstance(data, dict) and (
                            data.get("code") == code or data.get("status") == code
                        ):
                            _redis.delete(key)
                            count += 1
                    except Exception:
                        pass
        except Exception as e:
            print(f"⚠️ purge_by_code Redis: {e}", flush=True)
    return count

def delete_cache(url: str) -> bool:
    """Supprime une entrée par URL exacte (RAM + Redis)."""
    key = _key_url(url)
    deleted = False
    if key in _ram:
        del _ram[key]
        deleted = True
    if _redis_available:
        try:
            if _redis.delete(key):
                deleted = True
        except Exception:
            pass
    return deleted