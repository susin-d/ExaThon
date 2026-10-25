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
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1)

    def available(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False

    def enqueue_score(self, ticket_id: str) -> None:
        self.client.rpush(PENDING_QUEUE, json.dumps(asdict(Job("score_ticket", ticket_id))))

    def depth(self) -> int:
        try:
            return int(self.client.llen(PENDING_QUEUE))
        except redis.RedisError:
            return 0
