import json
from app.redis_client import redis

CACHE_TTL_SECONDS = 30

def _flights_cache_key(origin, destination, departure_date, limit, offset):
    return f"flights_cache:{origin}:{destination}:{departure_date}:{limit}:{offset}"

def get_cached_flights(key: str):
    raw = redis.get(key)
    return json.loads(raw) if raw else None

def set_cached_flights(key: str, data: list, ttl: int = CACHE_TTL_SECONDS):
    redis.set(key, json.dumps(data, default=str), ex=ttl)

def invalidate_flights_cache():
    """Called whenever a flight is created/modified — wipes all cached search results."""
    keys = redis.keys("flights_cache:*")
    if keys:
        redis.delete(*keys)