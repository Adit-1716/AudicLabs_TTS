import json

import redis

from app.config import settings

QUEUE = "transcribe-jobs"


def redis_client():
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )


def enqueue(media_file_id: str) -> None:
    redis_client().lpush(QUEUE, json.dumps({"media_file_id": media_file_id}))


def dequeue(timeout: int = 5) -> dict | None:
    item = redis_client().brpop(QUEUE, timeout=timeout)
    if not item:
        return None
    return json.loads(item[1])
