from datetime import UTC, datetime

from app.repository import DemoRepository
from app.schemas import TicketInput


def ticket(source_id: str = "NEW-1") -> TicketInput:
    return TicketInput(
        source_system="test",
        source_ticket_id=source_id,
        received_at=datetime.now(UTC),
        channel="app",
        branch_id="BR-001",
        product="Payments",
        agent_category="status",
        agent_type="query",
        resolution=None,
        escalated_to_io=False,
        text="UPI amount debited Rs 900 and reversal not credited after four days",
    )


def test_ingestion_is_idempotent_and_scoring_is_traceable(tmp_path):
    repo = DemoRepository(tmp_path / "demo.db")
    ids, duplicates = repo.ingest([ticket()])
    repeated, repeat_duplicates = repo.ingest([ticket()])
    assert len(ids) == 1 and duplicates == 0
    assert repeated == [] and repeat_duplicates == 1

    repo.score_ticket(ids[0])
    matches = [item for item in repo.review_queue(0.65) if item["ticket_id"] == ids[0]]
    assert matches[0]["model_version"] == "rules-tfidf-v1"
    assert matches[0]["trigger_phrase"]


def test_review_events_append_without_mutating_ticket(tmp_path):
    repo = DemoRepository(tmp_path / "demo.db")
    ids, _ = repo.ingest([ticket("REVIEW-1")])
    repo.score_ticket(ids[0])
    first = repo.add_review(ids[0], "reviewer-a", {"decision": "confirm", "reason": None})
    second = repo.add_review(ids[0], "reviewer-a", {"decision": "dismiss", "reason": "Customer asked only for status"})
    assert first["review_id"] != second["review_id"]
    with repo.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM review_events WHERE ticket_id=?", (ids[0],)).fetchone()[0] == 2
        assert "UPI amount debited" in db.execute("SELECT raw_text FROM tickets WHERE ticket_id=?", (ids[0],)).fetchone()[0]
