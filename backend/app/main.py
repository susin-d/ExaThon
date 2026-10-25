import csv
import io
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .auth import ActorContext, get_actor
from .queueing import QueueClient
from .repository import Repository, build_repository
from .schemas import BatchInput, BatchResult, ReviewInput, TicketInput
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.repository = build_repository(settings)
    app.state.queue = QueueClient(settings)
    yield


app = FastAPI(
    title="Complaint Root-Cause Engine API",
    version="0.1.0",
    description="Evidence-first complaint investigation with append-only human review.",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Actor-Id"],
)


def repository() -> Repository:
    return app.state.repository


def enqueue_or_score(repo: Repository, ticket_ids: list[str]) -> int:
    queue: QueueClient = app.state.queue
    queued = 0
    if queue.available():
        for ticket_id in ticket_ids:
            queue.enqueue_score(ticket_id)
            queued += 1
    else:
        for ticket_id in ticket_ids:
            repo.score_ticket(ticket_id)
    return queued


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": get_settings().data_backend}


@app.post("/api/v1/tickets/batch", response_model=BatchResult, status_code=status.HTTP_202_ACCEPTED)
def ingest_batch(payload: BatchInput, repo: Annotated[Repository, Depends(repository)]) -> BatchResult:
    ticket_ids, duplicates = repo.ingest(payload.tickets)
    queued = enqueue_or_score(repo, ticket_ids)
    return BatchResult(accepted=len(ticket_ids), duplicates=duplicates, queued=queued, ticket_ids=ticket_ids)


@app.post("/api/v1/imports/csv", status_code=status.HTTP_202_ACCEPTED)
async def import_csv(
    file: Annotated[UploadFile, File(description="UTF-8 CSV matching the ticket ingestion contract")],
    repo: Annotated[Repository, Depends(repository)],
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "Upload a .csv file.")
    raw = await file.read()
    if len(raw) > 15_000_000:
        raise HTTPException(413, "CSV exceeds the 15 MB phase-one import limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "CSV must be UTF-8 encoded.") from exc

    valid: list[TicketInput] = []
    errors: list[dict] = []
    for line_number, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        normalized = dict(row)
        normalized["escalated_to_io"] = str(row.get("escalated_to_io", "false")).lower() in {"1", "true", "yes"}
        try:
            valid.append(TicketInput.model_validate(normalized))
        except ValidationError as exc:
            errors.append({"row": line_number, "errors": exc.errors(include_url=False)})

    ticket_ids, duplicates = repo.ingest(valid) if valid else ([], 0)
    queued = enqueue_or_score(repo, ticket_ids)
    import_id = repo.create_import(file.filename, len(ticket_ids), errors)
    return {"import_id": import_id, "accepted": len(ticket_ids), "duplicates": duplicates, "queued": queued, "error_count": len(errors)}


@app.get("/api/v1/imports/{import_id}")
def get_import(import_id: str, repo: Annotated[Repository, Depends(repository)]) -> dict:
    result = repo.get_import(import_id)
    if not result:
        raise HTTPException(404, "Import not found.")
    return result


@app.get("/api/v1/pipeline/status")
def pipeline_status(repo: Annotated[Repository, Depends(repository)]) -> dict:
    return repo.pipeline_status(app.state.queue.depth())


@app.get("/api/v1/clusters")
def clusters(
    repo: Annotated[Repository, Depends(repository)],
    search: str | None = Query(default=None, max_length=120),
    product: str | None = Query(default=None, max_length=80),
) -> list[dict]:
    return repo.list_clusters(search=search, product=product)


@app.get("/api/v1/clusters/{cluster_id}")
def cluster_detail(cluster_id: str, repo: Annotated[Repository, Depends(repository)]) -> dict:
    result = repo.get_cluster(cluster_id)
    if not result:
        raise HTTPException(404, "Cluster not found.")
    return result


@app.get("/api/v1/review-queue")
def review_queue(
    repo: Annotated[Repository, Depends(repository)],
    minimum_confidence: float = Query(default=0.65, ge=0, le=1),
) -> list[dict]:
    return repo.review_queue(minimum_confidence)


@app.post("/api/v1/tickets/{ticket_id}/reviews", status_code=status.HTTP_201_CREATED)
def review_ticket(
    ticket_id: str,
    payload: ReviewInput,
    repo: Annotated[Repository, Depends(repository)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> dict:
    try:
        payload.validate_semantics()
        return repo.add_review(ticket_id, actor.actor_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "Ticket or prediction not found.") from exc
