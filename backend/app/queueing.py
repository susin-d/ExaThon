import json
from dataclasses import asdict, dataclass

import redis

from .settings import Settings

PENDING_QUEUE = "complaints:jobs:pending"
DEAD_QUEUE = "complaints:jobs:dead"


@dataclass
class Job:
    job_type: str
    ticket_id: str
    attempts: int = 0


class QueueClient:
    def __init__(self, settings: Settings):
        self.client = (
            redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1)
            if settings.queue_enabled and settings.redis_url
            else None
        )

    def available(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False

    def enqueue_score(self, ticket_id: str) -> None:
        if self.client is None:
            raise RuntimeError("Redis queue is disabled.")
        self.client.rpush(PENDING_QUEUE, json.dumps(asdict(Job("score_ticket", ticket_id))))

    def depth(self) -> int:
        if self.client is None:
            return 0
        try:
            return int(self.client.llen(PENDING_QUEUE))
        except redis.RedisError:
            return 0

    def pop(self) -> str | None:
        if self.client is None:
            return None
        try:
            return self.client.lpop(PENDING_QUEUE)
        except redis.RedisError:
            return None

    def retry_or_dead_letter(self, raw: str, error: Exception) -> None:
        if self.client is None:
            raise RuntimeError("Redis queue is disabled.")
        payload = json.loads(raw)
        payload["attempts"] = int(payload.get("attempts", 0)) + 1
        payload["last_error"] = str(error)
        target = DEAD_QUEUE if payload["attempts"] >= 3 else PENDING_QUEUE
        if target == PENDING_QUEUE:
            payload.pop("last_error", None)
        self.client.rpush(target, json.dumps(payload))
