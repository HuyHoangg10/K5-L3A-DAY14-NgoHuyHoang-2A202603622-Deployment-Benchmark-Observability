"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
Dùng connection pool cache theo REDIS_URL để tránh rò rỉ kết nối mỗi request.
"""
import os
import redis
from app.config import settings

_clients: dict[str, redis.Redis] = {}


def get_redis_client():
    url = os.getenv("REDIS_URL", settings.redis_url)
    if not url:
        return None
    client = _clients.get(url)
    if client is None:
        try:
            client = redis.from_url(
                url,
                decode_responses=True,
                socket_timeout=0.5,
                socket_connect_timeout=0.3,
                max_connections=20,
            )
            _clients[url] = client
        except Exception:
            return None
    return client


r = None


def redis_healthy() -> bool:
    try:
        client = get_redis_client()
        if client is None:
            return False
        return bool(client.ping())
    except Exception:
        return False
