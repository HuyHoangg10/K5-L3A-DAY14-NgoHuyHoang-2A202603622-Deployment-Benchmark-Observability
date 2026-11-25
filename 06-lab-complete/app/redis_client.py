"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import os
import redis
from app.config import settings


def get_redis_client():
    url = os.getenv("REDIS_URL", settings.redis_url)
    if not url:
        return None
    try:
        return redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.5,
            socket_connect_timeout=1.5,
        )
    except Exception:
        return None


r = get_redis_client()


def redis_healthy() -> bool:
    try:
        client = get_redis_client()
        if client is None:
            return False
        return bool(client.ping())
    except Exception:
        return False
