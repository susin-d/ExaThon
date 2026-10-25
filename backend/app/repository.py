import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .schemas import TicketInput
from .scoring import redact_excerpt, score_text
from .settings import Settings


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def onset_note_for(cluster_key: str) -> str:
    return {
        "upi_reversal": "Complaint volume accelerated in the current seven-day window; the suspected switch-change link remains unconfirmed.",
        "loan_reset": "The increase begins after the October rate-reset cycle; no single process change is confirmed yet.",
        "atm_debit": "Volume concentrates in Northstar-operated terminals; vendor causation remains unconfirmed.",
        "charges": "The series follows the fee-policy effective date and is declining from its initial peak.",
    }.get(cluster_key, "No external process change is linked to this cluster yet.")


class Repository(ABC):
    @abstractmethod
    def ingest(self, tickets: list[TicketInput]) -> tuple[list[str], int]: ...

    @abstractmethod
    def score_ticket(self, ticket_id: str) -> None: ...

    @abstractmethod
    def list_clusters(self, search: str | None = None, product: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_cluster(self, cluster_id: str) -> dict | None: ...

    @abstractmethod
    def review_queue(self, minimum_confidence: float) -> list[dict]: ...

    @abstractmethod
    def add_review(self, ticket_id: str, actor_id: str, payload: dict) -> dict: ...

    @abstractmethod
    def pipeline_status(self, queue_depth: int) -> dict: ...

    @abstractmethod
    def create_import(self, filename: str, accepted: int, errors: list[dict]) -> str: ...

    @abstractmethod
    def get_import(self, import_id: str) -> dict | None: ...

    @abstractmethod
    def escalation_gap(self) -> dict: ...

    @abstractmethod
    def top_grounds(self) -> list[dict]: ...

    @abstractmethod
    def ask_data(self, question: str) -> dict: ...


class DemoRepository(Repository):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    source_system TEXT NOT NULL,
                    source_ticket_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    branch_id TEXT NOT NULL,
                    product TEXT NOT NULL,
                    agent_category TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    resolution TEXT,
                    escalated_to_io INTEGER NOT NULL,
                    raw_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_system, source_ticket_id)
                );
                CREATE TABLE IF NOT EXISTS insights (
                    ticket_id TEXT PRIMARY KEY REFERENCES tickets(ticket_id),
                    is_complaint INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    trigger_phrase TEXT NOT NULL,
                    ground_pred TEXT NOT NULL,
                    cluster_key TEXT,
                    amount REAL,
                    transaction_reference TEXT,
                    explanation_type TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS clusters (
                    cluster_id TEXT PRIMARY KEY,
                    cluster_key TEXT UNIQUE NOT NULL,
                    label TEXT NOT NULL,
                    ground TEXT NOT NULL,
                    product TEXT NOT NULL,
                    wow_growth REAL NOT NULL,
                    first_seen TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    daily_counts TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    review_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
                    actor_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    corrected_type TEXT,
                    corrected_ground TEXT,
                    previous_prediction TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    processed_count INTEGER NOT NULL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS imports (
                    import_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    errors_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            count = db.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
            if not count:
                self._seed(db)
            else:
                db.execute(
                    "UPDATE clusters SET summary = ? WHERE cluster_key = 'upi_reversal'",
                    (
                        (
                            "Customer narratives show a sharp rise in delayed reversals across multiple branches; "
                            "the operational cause is still under investigation."
                        ),
                    ),
                )

    def _seed(self, db: sqlite3.Connection) -> None:
        from .settings import get_settings

        scale = get_settings().demo_scale
        data_path = Path(__file__).with_name("data") / "demo.json"
        with data_path.open(encoding="utf-8") as data_file:
            demo_data = json.load(data_file)
        today = datetime.now(UTC).date()
        for cluster in demo_data["clusters"]:
            db.execute(
                "INSERT INTO clusters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cluster["cluster_id"], cluster["cluster_key"], cluster["label"], cluster["ground"],
                 cluster["product"], cluster["wow_growth"],
                 str(today - timedelta(days=cluster["age_days"])), cluster["status"],
                 cluster["summary"], json.dumps(cluster["daily_counts"])),
            )

        for index, (source_id, channel, branch, product, category, agent_type, text) in enumerate(demo_data["samples"]):
            ticket_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "demo:" + source_id))
            received = datetime.now(UTC) - timedelta(hours=3 + index * 7)
            db.execute(
                """INSERT INTO tickets VALUES (?, 'demo', ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)""",
                (ticket_id, source_id, received.isoformat(), channel, branch, product, category, agent_type, text, now_iso()),
            )
            self._score_with_connection(db, ticket_id)
        for key, (count, product, agent_type, template) in demo_data["generated"].items():
            count *= scale
            for offset in range(count):
                source_id = f"SYN-{key.upper()}-{offset + 1:04d}"
                ticket_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "demo:" + source_id))
                received = datetime.now(UTC) - timedelta(hours=(offset % 96) + 1)
                branch = f"BR-{(offset % 40) + 1:03d}"
                text = f"{template} Reference {source_id}."
                db.execute(
                    """INSERT INTO tickets VALUES (?, 'synthetic', ?, ?, ?, ?, ?, 'generated holdout', ?, NULL, 0, ?, ?)""",
                    (ticket_id, source_id, received.isoformat(), demo_data["channels"][offset % len(demo_data["channels"])], branch, product, agent_type, text, now_iso()),
                )
                self._score_with_connection(db, ticket_id)
        db.execute(
            "INSERT INTO pipeline_runs VALUES (?, 'cluster_discovery', 'succeeded', ?, ?, 481, NULL)",
            (str(uuid.uuid4()), (datetime.now(UTC) - timedelta(minutes=11)).isoformat(), (datetime.now(UTC) - timedelta(minutes=9)).isoformat()),
        )

    def ingest(self, tickets: list[TicketInput]) -> tuple[list[str], int]:
        accepted: list[str] = []
        duplicates = 0
        with self.connect() as db:
            for ticket in tickets:
                ticket_id = str(uuid.uuid4())
                try:
                    db.execute(
                        """INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            ticket_id,
                            ticket.source_system,
                            ticket.source_ticket_id,
                            ticket.received_at.isoformat(),
                            ticket.channel,
                            ticket.branch_id,
                            ticket.product,
                            ticket.agent_category,
                            ticket.agent_type,
                            ticket.resolution,
                            int(ticket.escalated_to_io),
                            ticket.text,
                            now_iso(),
                        ),
                    )
                    accepted.append(ticket_id)
                except sqlite3.IntegrityError:
                    duplicates += 1
        return accepted, duplicates

    def _score_with_connection(self, db: sqlite3.Connection, ticket_id: str) -> None:
        row = db.execute("SELECT raw_text FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            raise KeyError(ticket_id)
        score = score_text(row["raw_text"])
        db.execute(
            """INSERT OR REPLACE INTO insights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                int(score.is_complaint),
                score.confidence,
                score.trigger_phrase,
                score.ground,
                score.cluster_key,
                score.amount,
                score.transaction_reference,
                score.explanation_type,
                score.model_version,
                now_iso(),
            ),
        )

    def score_ticket(self, ticket_id: str) -> None:
        with self.connect() as db:
            started = now_iso()
            run_id = str(uuid.uuid4())
            db.execute("INSERT INTO pipeline_runs VALUES (?, 'ticket_scoring', 'running', ?, NULL, 0, NULL)", (run_id, started))
            try:
                self._score_with_connection(db, ticket_id)
                db.execute("UPDATE pipeline_runs SET status='succeeded', finished_at=?, processed_count=1 WHERE run_id=?", (now_iso(), run_id))
            except Exception as exc:
                db.execute("UPDATE pipeline_runs SET status='failed', finished_at=?, error=? WHERE run_id=?", (now_iso(), str(exc), run_id))
                raise

    def list_clusters(self, search: str | None = None, product: str | None = None) -> list[dict]:
        clauses, params = [], []
        if search:
            clauses.append("LOWER(c.label || ' ' || c.ground) LIKE ?")
            params.append(f"%{search.lower()}%")
        if product:
            clauses.append("c.product = ?")
            params.append(product)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            rows = db.execute(
                f"""SELECT c.*, COUNT(i.ticket_id) AS size,
                    COUNT(DISTINCT t.branch_id) AS branch_count,
                    ROUND(AVG(i.confidence), 3) AS confidence
                    FROM clusters c
                    LEFT JOIN insights i ON i.cluster_key = c.cluster_key
                    LEFT JOIN tickets t ON t.ticket_id = i.ticket_id
                    {where}
                    GROUP BY c.cluster_id
                    ORDER BY size DESC, ABS(c.wow_growth) DESC""",
                params,
            ).fetchall()
        return [self._cluster_dict(row, rank + 1) for rank, row in enumerate(rows)]

    @staticmethod
    def _cluster_dict(row: sqlite3.Row, rank: int | None = None) -> dict:
        result = dict(row)
        result["daily_counts"] = json.loads(result["daily_counts"])
        result["rank"] = rank
        result["size"] = result.get("size", 0)
        result["branch_count"] = result.get("branch_count", 0)
        result["confidence"] = result.get("confidence") or 0.0
        result["onset_note"] = onset_note_for(result["cluster_key"])
        return result

    def get_cluster(self, cluster_id: str) -> dict | None:
        with self.connect() as db:
            cluster = db.execute(
                """SELECT c.*, COUNT(i.ticket_id) AS size, COUNT(DISTINCT t.branch_id) AS branch_count,
                    ROUND(AVG(i.confidence), 3) AS confidence
                    FROM clusters c LEFT JOIN insights i ON i.cluster_key=c.cluster_key
                    LEFT JOIN tickets t ON t.ticket_id=i.ticket_id
                    WHERE c.cluster_id=? GROUP BY c.cluster_id""",
                (cluster_id,),
            ).fetchone()
            if not cluster:
                return None
            tickets = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.received_at, t.channel, t.branch_id,
                    t.product, t.agent_type, t.raw_text, i.confidence, i.trigger_phrase,
                    i.ground_pred, i.model_version, i.processed_at
                    FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                    WHERE i.cluster_key=? ORDER BY i.confidence DESC LIMIT 25""",
                (cluster["cluster_key"],),
            ).fetchall()
            branches = db.execute(
                """SELECT t.branch_id, COUNT(*) AS count FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                    WHERE i.cluster_key=? GROUP BY t.branch_id ORDER BY count DESC LIMIT 5""",
                (cluster["cluster_key"],),
            ).fetchall()
        result = self._cluster_dict(cluster)
        result["top_branches"] = [dict(row) for row in branches]
        result["tickets"] = [self._ticket_dict(row) for row in tickets]
        return result

    @staticmethod
    def _ticket_dict(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["excerpt"] = redact_excerpt(result.pop("raw_text"))
        result["confidence"] = round(result["confidence"], 3)
        return result

    def review_queue(self, minimum_confidence: float) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.received_at, t.channel, t.branch_id,
                    t.product, t.agent_type, t.raw_text, i.confidence, i.trigger_phrase,
                    i.ground_pred, i.model_version, i.processed_at,
                    (SELECT decision FROM review_events r WHERE r.ticket_id=t.ticket_id ORDER BY created_at DESC LIMIT 1) AS review_state
                    FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                    WHERE t.agent_type IN ('query','request') AND i.is_complaint=1 AND i.confidence>=?
                    ORDER BY i.confidence DESC, t.received_at DESC""",
                (minimum_confidence,),
            ).fetchall()
        return [self._ticket_dict(row) for row in rows]

    def add_review(self, ticket_id: str, actor_id: str, payload: dict) -> dict:
        with self.connect() as db:
            insight = db.execute("SELECT * FROM insights WHERE ticket_id=?", (ticket_id,)).fetchone()
            if not insight:
                raise KeyError(ticket_id)
            review = {
                "review_id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "actor_id": actor_id,
                "decision": payload["decision"],
                "reason": payload.get("reason"),
                "corrected_type": payload.get("corrected_type"),
                "corrected_ground": payload.get("corrected_ground"),
                "previous_prediction": json.dumps({"is_complaint": bool(insight["is_complaint"]), "ground": insight["ground_pred"], "confidence": insight["confidence"]}),
                "model_version": insight["model_version"],
                "created_at": now_iso(),
            }
            db.execute(
                """INSERT INTO review_events VALUES (:review_id, :ticket_id, :actor_id, :decision,
                    :reason, :corrected_type, :corrected_ground, :previous_prediction,
                    :model_version, :created_at)""",
                review,
            )
        return review

    def pipeline_status(self, queue_depth: int) -> dict:
        with self.connect() as db:
            ticket_count = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            scored_count = db.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
            review_count = db.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]
            review_queue_count = db.execute(
                """SELECT COUNT(*) FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                WHERE t.agent_type IN ('query','request') AND i.is_complaint=1
                AND NOT EXISTS (
                    SELECT 1 FROM review_events r WHERE r.ticket_id=t.ticket_id
                    AND r.decision IN ('confirm','dismiss','reclassify')
                )"""
            ).fetchone()[0]
            last_run = db.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            failures = db.execute("SELECT COUNT(*) FROM pipeline_runs WHERE status='failed'").fetchone()[0]
        last = dict(last_run) if last_run else None
        return {
            "backend": "demo",
            "queue_depth": queue_depth,
            "tickets_total": ticket_count,
            "tickets_scored": scored_count,
            "reviews_recorded": review_count,
            "review_queue_count": review_queue_count,
            "active_model": "rules-tfidf-v1",
            "last_successful_run": last,
            "failed_runs": failures,
            "freshness": "current" if queue_depth == 0 else "processing",
            "stages": [
                {"name": "Ingested", "value": ticket_count, "state": "complete"},
                {"name": "Scored", "value": scored_count, "state": "complete" if scored_count == ticket_count else "active"},
                {"name": "Clustered", "value": max(0, scored_count - queue_depth), "state": "complete"},
                {"name": "Reviewed", "value": review_count, "state": "waiting" if review_count == 0 else "complete"},
            ],
        }

    def create_import(self, filename: str, accepted: int, errors: list[dict]) -> str:
        import_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?)", (import_id, filename, "completed_with_errors" if errors else "completed", accepted, json.dumps(errors), now_iso()))
        return import_id

    def get_import(self, import_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM imports WHERE import_id=?", (import_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["errors"] = json.loads(result.pop("errors_json"))
        return result

    def escalation_gap(self) -> dict:
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.ticket_id, t.source_ticket_id, t.branch_id, t.product, t.agent_type,
                    t.raw_text, i.confidence, i.ground_pred, i.trigger_phrase
                    FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                    WHERE i.is_complaint=1 AND t.escalated_to_io=0
                    AND (t.resolution IS NULL OR LOWER(t.resolution) LIKE '%reject%'
                         OR LOWER(t.resolution) LIKE '%partial%')
                    ORDER BY i.confidence DESC LIMIT 50"""
            ).fetchall()
            total = db.execute(
                """SELECT COUNT(*) FROM tickets t JOIN insights i ON i.ticket_id=t.ticket_id
                   WHERE i.is_complaint=1 AND t.escalated_to_io=0
                   AND (t.resolution IS NULL OR LOWER(t.resolution) LIKE '%reject%'
                        OR LOWER(t.resolution) LIKE '%partial%')"""
            ).fetchone()[0]
        items = []
        for row in rows:
            item = dict(row)
            item["excerpt"] = redact_excerpt(item.pop("raw_text"))
            items.append(item)
        return {
            "total": total,
            "high_confidence": sum(item["confidence"] >= 0.8 for item in items),
            "items": items,
            "explanation": "Complaint-like tickets marked unresolved or rejected without an Internal Ombudsman escalation.",
        }

    def top_grounds(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT i.ground_pred AS ground, COUNT(*) AS complaint_count,
                    ROUND(AVG(i.confidence), 3) AS confidence
                    FROM insights i WHERE i.is_complaint=1
                    GROUP BY i.ground_pred ORDER BY complaint_count DESC LIMIT 5"""
            ).fetchall()
        total = sum(row["complaint_count"] for row in rows) or 1
        return [
            {**dict(row), "share": round(row["complaint_count"] / total, 3), "rank": index + 1}
            for index, row in enumerate(rows)
        ]

    def ask_data(self, question: str) -> dict:
        normalized = question.lower().strip()
        if not normalized:
            raise ValueError("Ask a question about branches, clusters, grounds, or escalation.")
        if "ground" in normalized or "top five" in normalized:
            return {"question": question, "answer": "Top complaint grounds ranked by model evidence.", "data": self.top_grounds(), "source": "TICKET_INSIGHTS"}
        if "escalat" in normalized or "ombudsman" in normalized or "reject" in normalized:
            result = self.escalation_gap()
            return {"question": question, "answer": f"{result['total']} complaint-like tickets appear unresolved without an ombudsman escalation.", "data": result, "source": "TICKETS + TICKET_INSIGHTS"}
        if "branch" in normalized or "atm" in normalized:
            clusters = self.list_clusters(search="ATM" if "atm" in normalized else None)
            return {"question": question, "answer": "The highest-volume branches are shown in the matching root-cause cluster.", "data": clusters[:3], "source": "CLUSTERS + TICKET_INSIGHTS"}
        raise ValueError("Supported questions cover top grounds, escalation gaps, complaint clusters, and affected branches.")


class ExasolRepository(Repository):
    """Production adapter. SQL assets define the contract; live verification requires credentials."""

    def __init__(self, settings: Settings):
        if not all((settings.exasol_dsn, settings.exasol_user, settings.exasol_password)):
            raise RuntimeError("EXASOL_DSN, EXASOL_USER and EXASOL_PASSWORD are required")
        import pyexasol

        self.schema = settings.exasol_schema
        self.connection = pyexasol.connect(
            dsn=settings.exasol_dsn,
            user=settings.exasol_user,
            password=settings.exasol_password,
            schema=self.schema,
            compression=True,
        )

    def _all(self, sql: str, params: dict | None = None) -> list[dict]:
        statement = self.connection.execute(sql, params or {})
        names = [str(name).lower() for name in statement.columns()]
        return [dict(zip(names, row, strict=True)) for row in statement.fetchall()]

    def ingest(self, tickets: list[TicketInput]) -> tuple[list[str], int]:
        accepted, duplicates = [], 0
        for ticket in tickets:
            exists = self.connection.execute(
                "SELECT COUNT(*) FROM TICKETS WHERE SOURCE_SYSTEM=:s AND SOURCE_TICKET_ID=:i",
                {"s": ticket.source_system, "i": ticket.source_ticket_id},
            ).fetchval()
            if exists:
                duplicates += 1
                continue
            ticket_id = str(uuid.uuid4())
            payload = ticket.model_dump()
            payload.update(ticket_id=ticket_id, received_at=ticket.received_at, raw_text=payload.pop("text"))
            self.connection.execute(
                """INSERT INTO TICKETS (TICKET_ID,SOURCE_SYSTEM,SOURCE_TICKET_ID,RECEIVED_AT,CHANNEL,
                BRANCH_ID,PRODUCT,AGENT_CATEGORY,AGENT_TYPE,RESOLUTION,ESCALATED_TO_IO,RAW_TEXT,CREATED_AT)
                VALUES (:ticket_id,:source_system,:source_ticket_id,:received_at,:channel,:branch_id,:product,
                :agent_category,:agent_type,:resolution,:escalated_to_io,:raw_text,CURRENT_TIMESTAMP)""",
                payload,
            )
            accepted.append(ticket_id)
        return accepted, duplicates

    def score_ticket(self, ticket_id: str) -> None:
        self.connection.execute("EXECUTE SCRIPT SCORE_AND_STORE_TICKET(:id)", {"id": ticket_id})

    def list_clusters(self, search: str | None = None, product: str | None = None) -> list[dict]:
        return self._all("SELECT * FROM V_CLUSTER_BOARD WHERE (:q IS NULL OR LOWER(LABEL) LIKE LOWER('%'||:q||'%')) AND (:p IS NULL OR PRODUCT=:p) ORDER BY SIZE DESC, ABS(WOW_GROWTH) DESC", {"q": search, "p": product})

    def get_cluster(self, cluster_id: str) -> dict | None:
        rows = self._all("SELECT * FROM V_CLUSTER_BOARD WHERE CLUSTER_ID=:id", {"id": cluster_id})
        if not rows:
            return None
        cluster = rows[0]
        cluster["onset_note"] = onset_note_for(cluster["cluster_key"])
        cluster["daily_counts"] = [
            row["count"]
            for row in self._all(
                """SELECT TRUNC(t.RECEIVED_AT) DAY, COUNT(*) COUNT
                FROM TICKETS t JOIN CLUSTER_MEMBERSHIPS cm ON cm.TICKET_ID=t.TICKET_ID
                WHERE cm.CLUSTER_ID=:id AND t.RECEIVED_AT >= CURRENT_DATE - 6
                GROUP BY TRUNC(t.RECEIVED_AT) ORDER BY DAY""",
                {"id": cluster_id},
            )
        ]
        cluster["top_branches"] = self._all(
            """SELECT t.BRANCH_ID, COUNT(*) COUNT
            FROM TICKETS t JOIN CLUSTER_MEMBERSHIPS cm ON cm.TICKET_ID=t.TICKET_ID
            WHERE cm.CLUSTER_ID=:id GROUP BY t.BRANCH_ID ORDER BY COUNT DESC LIMIT 5""",
            {"id": cluster_id},
        )
        cluster["tickets"] = self._all(
            """SELECT t.TICKET_ID, t.SOURCE_TICKET_ID, t.RECEIVED_AT, t.CHANNEL, t.BRANCH_ID,
            t.PRODUCT, t.AGENT_TYPE,
            SUBSTR(REGEXP_REPLACE(t.RAW_TEXT, '\\b[0-9]{10,16}\\b', 'REDACTED'), 1, 260) EXCERPT,
            i.CONFIDENCE, i.TRIGGER_PHRASE, i.GROUND_PRED, i.MODEL_VERSION, i.PROCESSED_AT
            FROM TICKETS t JOIN TICKET_INSIGHTS i ON i.TICKET_ID=t.TICKET_ID
            JOIN CLUSTER_MEMBERSHIPS cm ON cm.TICKET_ID=t.TICKET_ID
            WHERE cm.CLUSTER_ID=:id ORDER BY i.CONFIDENCE DESC LIMIT 25""",
            {"id": cluster_id},
        )
        return cluster

    def review_queue(self, minimum_confidence: float) -> list[dict]:
        return self._all("SELECT * FROM V_REVIEW_QUEUE WHERE CONFIDENCE>=:c ORDER BY CONFIDENCE DESC", {"c": minimum_confidence})

    def add_review(self, ticket_id: str, actor_id: str, payload: dict) -> dict:
        review_id = str(uuid.uuid4())
        params = {**payload, "review_id": review_id, "ticket_id": ticket_id, "actor_id": actor_id}
        self.connection.execute("EXECUTE SCRIPT APPEND_REVIEW_EVENT(:review_id,:ticket_id,:actor_id,:decision,:reason,:corrected_type,:corrected_ground)", params)
        return {**params, "created_at": now_iso()}

    def pipeline_status(self, queue_depth: int) -> dict:
        rows = self._all("SELECT * FROM V_PIPELINE_STATUS")
        result = rows[0] if rows else {}
        result["queue_depth"] = queue_depth
        result["backend"] = "exasol"
        total = int(result.get("tickets_total", 0))
        scored = int(result.get("tickets_scored", 0))
        reviewed = int(result.get("reviews_recorded", 0))
        result["review_queue_count"] = int(
            self.connection.execute("SELECT COUNT(*) FROM V_REVIEW_QUEUE").fetchval()
        )
        result["freshness"] = "current" if queue_depth == 0 else "processing"
        result["stages"] = [
            {"name": "Ingested", "value": total, "state": "complete"},
            {"name": "Scored", "value": scored, "state": "complete" if scored == total else "active"},
            {"name": "Clustered", "value": scored, "state": "complete"},
            {"name": "Reviewed", "value": reviewed, "state": "complete" if reviewed else "waiting"},
        ]
        return result

    def create_import(self, filename: str, accepted: int, errors: list[dict]) -> str:
        import_id = str(uuid.uuid4())
        self.connection.execute("INSERT INTO IMPORTS VALUES (:id,:name,:status,:accepted,:errors,CURRENT_TIMESTAMP)", {"id": import_id, "name": filename, "status": "completed_with_errors" if errors else "completed", "accepted": accepted, "errors": json.dumps(errors)})
        return import_id

    def get_import(self, import_id: str) -> dict | None:
        rows = self._all("SELECT * FROM IMPORTS WHERE IMPORT_ID=:id", {"id": import_id})
        return rows[0] if rows else None

    def escalation_gap(self) -> dict:
        rows = self._all("SELECT * FROM V_ESCALATION_GAP")
        return {"total": len(rows), "high_confidence": len(rows), "items": rows, "explanation": "Exasol escalation-gap view."}

    def top_grounds(self) -> list[dict]:
        return self._all("SELECT * FROM V_TOP_GROUNDS ORDER BY COMPLAINT_COUNT DESC LIMIT 5")

    def ask_data(self, question: str) -> dict:
        return {"question": question, "answer": "Use the configured Exasol MCP read-only connection for this question.", "data": [], "source": "EXASOL"}


def build_repository(settings: Settings) -> Repository:
    if settings.data_backend.lower() == "supabase":
        from .supabase_repository import SupabaseRepository

        return SupabaseRepository(settings)
    if settings.data_backend.lower() == "exasol":
        return ExasolRepository(settings)
    return DemoRepository(settings.demo_db_path)
