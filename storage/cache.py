import json
import hashlib
import redis

r = redis.Redis(host="redis", port=6379, db=0)


def make_key(url: str):
    return "video:" + hashlib.md5(url.encode()).hexdigest()


def get_cache(url: str):
    key = make_key(url)
    data = r.get(key)
    if data:
        return json.loads(data)
    return None


def set_cache(url: str, value: dict, ttl=3600 * 24 * 7):
    key = make_key(url)
    r.setex(key, ttl, json.dumps(value))