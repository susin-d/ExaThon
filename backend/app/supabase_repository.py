import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .repository import Repository, onset_note_for
from .schemas import TicketInput
from .scoring import redact_excerpt, score_text
from .settings import Settings


class SupabaseRepository(Repository):
    """Postgres adapter for a Supabase project."""

    def __init__(self, settings: Settings):
        if not settings.supabase_db_url:
            raise RuntimeError("SUPABASE_DB_URL is required when DATA_BACKEND=supabase")
        self.database_url = settings.supabase_db_url

    @contextmanager
    def connect(self):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def ingest(self, tickets: list[TicketInput]) -> tuple[list[str], int]:
        accepted: list[str] = []
        duplicates = 0
        with self.connect() as db:
            for ticket in tickets:
                ticket_id = str(uuid.uuid4())
                row = db.execute(
                    """INSERT INTO tickets
                    (ticket_id, source_system, source_ticket_id, received_at, channel, branch_id,
                     product, agent_category, agent_type, resolution, escalated_to_io, raw_text, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_system, source_ticket_id) DO NOTHING
                    RETURNING ticket_id""",
                    (ticket_id, ticket.source_system, ticket.source_ticket_id, ticket.received_at,
                     ticket.channel, ticket.branch_id, ticket.product, ticket.agent_category,
                     ticket.agent_type, ticket.resolution, ticket.escalated_to_io, ticket.text,
                     datetime.now(UTC)),
                ).fetchone()
                if row:
                    accepted.append(row["ticket_id"])
                else:
                    duplicates += 1
        return accepted, duplicates

    def score_ticket(self, ticket_id: str) -> None:
        started = datetime.now(UTC)
        run_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                "INSERT INTO pipeline_runs (run_id, run_type, status, started_at, processed_count) VALUES (%s, %s, %s, %s, %s)",
                (run_id, "ticket_scoring", "running", started, 0),
            )
            try:
                ticket = db.execute("SELECT raw_text FROM tickets WHERE ticket_id=%s", (ticket_id,)).fetchone()
                if not ticket:
                    raise KeyError(ticket_id)
                score = score_text(ticket["raw_text"])
                db.execute(
                    """INSERT INTO insights
                    (ticket_id, is_complaint, confidence, trigger_phrase, ground_pred, cluster_key,
                     amount, transaction_reference, explanation_type, model_version, processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticket_id) DO UPDATE SET
                    is_complaint=EXCLUDED.is_complaint, confidence=EXCLUDED.confidence,
                    trigger_phrase=EXCLUDED.trigger_phrase, ground_pred=EXCLUDED.ground_pred,
                    cluster_key=EXCLUDED.cluster_key, amount=EXCLUDED.amount,
                    transaction_reference=EXCLUDED.transaction_reference,
                    explanation_type=EXCLUDED.explanation_type,
                    model_version=EXCLUDED.model_version, processed_at=EXCLUDED.processed_at""",
                    (ticket_id, score.is_complaint, score.confidence, score.trigger_phrase,
                     score.ground, score.cluster_key, score.amount, score.transaction_reference,
                     score.explanation_type, score.model_version, datetime.now(UTC)),
                )
                db.execute(
                    "UPDATE pipeline_runs SET status='succeeded', finished_at=%s, processed_count=1 WHERE run_id=%s",
                    (datetime.now(UTC), run_id),
                )
            except Exception as exc:
                db.execute(
                    "UPDATE pipeline_runs SET status='failed', finished_at=%s, error=%s WHERE run_id=%s",
                    (datetime.now(UTC), str(exc), run_id),
                )
                raise

    @staticmethod
    def _cluster(row: dict[str, Any], rank: int | None = None) -> dict:
        result = dict(row)
        if isinstance(result.get("daily_counts"), str):
            result["daily_counts"] = json.loads(result["daily_counts"])
        result.update(rank=rank, size=result.get("size", 0), branch_count=result.get("branch_count", 0),
                      confidence=result.get("confidence") or 0.0,
                      onset_note=onset_note_for(result["cluster_key"]))
        return result

    @staticmethod
    def _ticket(row: dict[str, Any]) -> dict:
        result = dict(row)
        result["excerpt"] = redact_excerpt(result.pop("raw_text", result.pop("excerpt", "")))
        result["confidence"] = round(result["confidence"], 3)
        return result

    def list_clusters(self, search: str | None = None, product: str | None = None) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT c.*, COUNT(i.ticket_id) AS size, COUNT(DISTINCT t.branch_id) AS branch_count,
                   ROUND(AVG(i.confidence)::numeric, 3) AS confidence
                   FROM clusters c LEFT JOIN insights i ON i.cluster_key=c.cluster_key
                   LEFT JOIN tickets t ON t.ticket_id=i.ticket_id
                   WHERE (%s IS NULL OR LOWER(c.label || ' ' || c.ground) LIKE LOWER('%%' || %s || '%%'))
                     AND (%s IS NULL OR c.product=%s)
                   GROUP BY c.cluster_id ORDER BY size DESC, ABS(c.wow_growth) DESC""",
                (search, search, product, product),
            ).fetchall()
        return [self._cluster(row, index + 1) for index, row in enumerate(rows)]

    def get_cluster(self, cluster_id: str) -> dict | None:
        with self.connect() as db:
            cluster = db.execute(
                """SELECT c.*, COUNT(i.ticket_id) AS size, COUNT(DISTINCT t.branch_id) AS branch_count,
                   ROUND(AVG(i.confidence)::numeric, 3) AS confidence
                   FROM clusters c LEFT JOIN insights i ON i.cluster_key=c.cluster_key
                   LEFT JOIN tickets t ON t.ticket_id=i.ticket_id
                   WHERE c.cluster_id=%s GROUP BY c.cluster_id""", (cluster_id,),
            ).fetchone()
            if not cluster:
                return None
            tickets = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.received_at, t.channel, t.branch_id,
                   t.product, t.agent_type, t.raw_text, i.confidence, i.trigger_phrase,
                   i.ground_pred, i.model_version, i.processed_at
                   FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE i.cluster_key=%s ORDER BY i.confidence DESC LIMIT 25""",
                (cluster["cluster_key"],),
            ).fetchall()
            branches = db.execute(
                """SELECT t.branch_id, COUNT(*) AS count FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE i.cluster_key=%s GROUP BY t.branch_id ORDER BY count DESC LIMIT 5""",
                (cluster["cluster_key"],),
            ).fetchall()
        result = self._cluster(cluster)
        result["top_branches"] = [dict(row) for row in branches]
        result["tickets"] = [self._ticket(row) for row in tickets]
        return result

    def review_queue(self, minimum_confidence: float) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.received_at, t.channel, t.branch_id,
                   t.product, t.agent_type, t.raw_text, i.confidence, i.trigger_phrase,
                   i.ground_pred, i.model_version, i.processed_at,
                   (SELECT decision FROM review_events r WHERE r.ticket_id=t.ticket_id
                    ORDER BY created_at DESC LIMIT 1) AS review_state
                   FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE t.agent_type IN ('query','request') AND i.is_complaint
                     AND i.confidence >= %s ORDER BY i.confidence DESC, t.received_at DESC""",
                (minimum_confidence,),
            ).fetchall()
        return [self._ticket(row) for row in rows]

    def add_review(self, ticket_id: str, actor_id: str, payload: dict) -> dict:
        with self.connect() as db:
            insight = db.execute("SELECT * FROM insights WHERE ticket_id=%s", (ticket_id,)).fetchone()
            if not insight:
                raise KeyError(ticket_id)
            review = {
                "review_id": str(uuid.uuid4()), "ticket_id": ticket_id, "actor_id": actor_id,
                "decision": payload["decision"], "reason": payload.get("reason"),
                "corrected_type": payload.get("corrected_type"),
                "corrected_ground": payload.get("corrected_ground"),
                "previous_prediction": json.dumps({"is_complaint": bool(insight["is_complaint"]),
                    "ground": insight["ground_pred"], "confidence": insight["confidence"]}),
                "model_version": insight["model_version"], "created_at": datetime.now(UTC),
            }
            db.execute(
                """INSERT INTO review_events
                (review_id, ticket_id, actor_id, decision, reason, corrected_type, corrected_ground,
                 previous_prediction, model_version, created_at)
                VALUES (%(review_id)s, %(ticket_id)s, %(actor_id)s, %(decision)s, %(reason)s,
                        %(corrected_type)s, %(corrected_ground)s, %(previous_prediction)s,
                        %(model_version)s, %(created_at)s)""", review,
            )
        review["created_at"] = review["created_at"].isoformat()
        return review

    def pipeline_status(self, queue_depth: int) -> dict:
        with self.connect() as db:
            values = db.execute(
                """SELECT (SELECT COUNT(*) FROM tickets) AS tickets_total,
                   (SELECT COUNT(*) FROM insights) AS tickets_scored,
                   (SELECT COUNT(*) FROM review_events) AS reviews_recorded,
                   (SELECT MAX(finished_at) FROM pipeline_runs WHERE status='succeeded') AS last_finished_at,
                   (SELECT COUNT(*) FROM pipeline_runs WHERE status='failed') AS failed_runs""",
            ).fetchone()
            review_queue = db.execute(
                """SELECT COUNT(*) AS count FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE t.agent_type IN ('query','request') AND i.is_complaint
                   AND NOT EXISTS (SELECT 1 FROM review_events r WHERE r.ticket_id=t.ticket_id)""",
            ).fetchone()["count"]
        total, scored, reviewed = (int(values[key]) for key in ("tickets_total", "tickets_scored", "reviews_recorded"))
        last = {"finished_at": values["last_finished_at"].isoformat()} if values["last_finished_at"] else None
        return {
            "backend": "supabase", "queue_depth": queue_depth, "tickets_total": total,
            "tickets_scored": scored, "reviews_recorded": reviewed, "review_queue_count": review_queue,
            "active_model": "rules-tfidf-v1", "last_successful_run": last,
            "failed_runs": int(values["failed_runs"]), "freshness": "current" if queue_depth == 0 else "processing",
            "stages": [{"name": "Ingested", "value": total, "state": "complete"},
                        {"name": "Scored", "value": scored, "state": "complete" if scored == total else "active"},
                        {"name": "Clustered", "value": scored, "state": "complete"},
                        {"name": "Reviewed", "value": reviewed, "state": "complete" if reviewed else "waiting"}],
        }

    def create_import(self, filename: str, accepted: int, errors: list[dict]) -> str:
        import_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                "INSERT INTO imports (import_id, filename, status, accepted, errors_json, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (import_id, filename, "completed_with_errors" if errors else "completed", accepted,
                 json.dumps(errors), datetime.now(UTC)),
            )
        return import_id

    def get_import(self, import_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM imports WHERE import_id=%s", (import_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        errors = result.pop("errors_json")
        result["errors"] = json.loads(errors) if isinstance(errors, str) else errors
        return result

    def escalation_gap(self) -> dict:
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.branch_id, t.product, t.agent_type,
                   t.raw_text, i.confidence, i.ground_pred, i.trigger_phrase
                   FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE i.is_complaint AND NOT t.escalated_to_io
                   AND (t.resolution IS NULL OR LOWER(t.resolution) LIKE '%reject%'
                        OR LOWER(t.resolution) LIKE '%partial%')
                   ORDER BY i.confidence DESC LIMIT 50"""
            ).fetchall()
        items = [self._ticket(row) for row in rows]
        return {"total": len(items), "high_confidence": sum(i["confidence"] >= 0.8 for i in items),
                "items": items, "explanation": "Complaint-like tickets without an ombudsman escalation."}

    def top_grounds(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT ground_pred AS ground, COUNT(*) AS complaint_count,
                   ROUND(AVG(confidence)::numeric, 3) AS confidence
                   FROM insights WHERE is_complaint GROUP BY ground_pred
                   ORDER BY complaint_count DESC LIMIT 5"""
            ).fetchall()
        total = sum(row["complaint_count"] for row in rows) or 1
        return [{**dict(row), "share": round(row["complaint_count"] / total, 3), "rank": i + 1}
                for i, row in enumerate(rows)]

    def ask_data(self, question: str) -> dict:
        normalized = question.lower()
        if "ground" in normalized or "top five" in normalized:
            return {"question": question, "answer": "Top complaint grounds ranked by model evidence.",
                    "data": self.top_grounds(), "source": "INSIGHTS"}
        if "escalat" in normalized or "ombudsman" in normalized:
            result = self.escalation_gap()
            return {"question": question, "answer": f"{result['total']} complaint-like tickets need escalation review.",
                    "data": result, "source": "TICKETS + INSIGHTS"}
        raise ValueError("Supported questions cover top grounds and escalation gaps.")
