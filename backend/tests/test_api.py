from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.auth import get_actor
from app.main import app
from app.repository import DemoRepository


class OfflineQueue:
    def available(self) -> bool:
        return False

    def depth(self) -> int:
        return 0


def test_demo_actor_is_selected_from_configured_users(monkeypatch):
    monkeypatch.setattr("app.auth.choice", lambda users: users[1])
    assert get_actor(None).actor_id == "vigneshwaran7002@gmail.com"


def payload(source_id: str = "API-1") -> dict:
    return {
        "source_system": "api-test",
        "source_ticket_id": source_id,
        "received_at": datetime.now(UTC).isoformat(),
        "channel": "app",
        "branch_id": "BR-008",
        "product": "Payments",
        "agent_category": "status",
        "agent_type": "query",
        "resolution": None,
        "escalated_to_io": False,
        "text": "UPI amount debited Rs 1200 and reversal not credited after four days",
    }


def test_api_vertical_slice(tmp_path):
    with TestClient(app) as client:
        app.state.repository = DemoRepository(tmp_path / "api.db")
        app.state.queue = OfflineQueue()

        first = client.post("/api/v1/tickets/batch", json={"tickets": [payload()]})
        duplicate = client.post("/api/v1/tickets/batch", json={"tickets": [payload()]})
        assert first.status_code == 202
        assert first.json()["accepted"] == 1
        assert duplicate.json()["duplicates"] == 1

        ticket_id = first.json()["ticket_ids"][0]
        queue = client.get("/api/v1/review-queue").json()
        assert any(item["ticket_id"] == ticket_id for item in queue)

        missing_reason = client.post(
            f"/api/v1/tickets/{ticket_id}/reviews",
            json={"decision": "dismiss"},
        )
        assert missing_reason.status_code == 422

        reviewed = client.post(
            f"/api/v1/tickets/{ticket_id}/reviews",
            headers={"X-Actor-Id": "ombudsman.test"},
            json={"decision": "confirm"},
        )
        assert reviewed.status_code == 201
        assert reviewed.json()["actor_id"] == "ombudsman.test"

        clusters = client.get("/api/v1/clusters").json()
        detail = client.get(f"/api/v1/clusters/{clusters[0]['cluster_id']}")
        assert detail.status_code == 200
        assert detail.json()["tickets"]

        status = client.get("/api/v1/pipeline/status").json()
        assert status["tickets_scored"] == status["tickets_total"]
        assert status["review_queue_count"] >= 1
