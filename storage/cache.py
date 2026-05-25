import hashlib

_cache = {}  # fallback RAM (Render safe)


def make_key(url: str):
    return "video:" + hashlib.md5(url.encode()).hexdigest()


def get_cache(url: str):
    key = make_key(url)
    return _cache.get(key)


def set_cache(url: str, value):
    key = make_key(url)
    _cache[key] = value