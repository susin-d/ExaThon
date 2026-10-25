import json
import logging
import signal

import redis

from .queueing import PENDING_QUEUE, Job, QueueClient
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
    if not settings.queue_enabled:
        logger.info("worker disabled because QUEUE_ENABLED=false")
        return
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
            queue = QueueClient(settings)
            queue.retry_or_dead_letter(raw, exc)


if __name__ == "__main__":
    main()
