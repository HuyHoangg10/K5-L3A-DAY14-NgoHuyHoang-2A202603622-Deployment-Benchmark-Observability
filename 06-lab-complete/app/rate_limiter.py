"""
Rate limiting (tiêu chí 7).
"""
import os
import time
import uuid
from fastapi import HTTPException
from app.config import settings
from app.redis_client import get_redis_client


def check_rate_limit(key: str) -> None:
    """Sliding window rate limit bằng Redis sorted set."""
    client = get_redis_client()
    if client is None:
        return

    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", str(settings.rate_limit_per_minute)))
    redis_key = f"rate_limit:{key}"
    now = time.time()
    window = 60.0
    member = f"{now}:{uuid.uuid4().hex}"

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zcard(redis_key)
        results = pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                headers={"Retry-After": "60"},
            )

        pipe = client.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, int(window) + 10)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        pass
