import json
import logging
import signal

import redis

from .queueing import DEAD_QUEUE, PENDING_QUEUE, Job
from .repository import build_repository
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("complaint-worker")
running = True


def stop(*_: object) -> None:
    global running
    running = False


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    settings = get_settings()
    repository = build_repository(settings)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("worker ready backend=%s", settings.data_backend)

    while running:
        item = client.blpop(PENDING_QUEUE, timeout=2)
        if not item:
            continue
        _, raw = item
        try:
            job = Job(**json.loads(raw))
            if job.job_type != "score_ticket":
                raise ValueError(f"Unsupported job type: {job.job_type}")
            repository.score_ticket(job.ticket_id)
            logger.info("scored ticket=%s", job.ticket_id)
        except Exception as exc:
            logger.exception("job failed")
            payload = json.loads(raw)
            payload["attempts"] = int(payload.get("attempts", 0)) + 1
            payload["last_error"] = str(exc)
            if payload["attempts"] >= 3:
                client.rpush(DEAD_QUEUE, json.dumps(payload))
            else:
                payload.pop("last_error", None)
                client.rpush(PENDING_QUEUE, json.dumps(payload))


if __name__ == "__main__":
    main()
