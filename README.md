# Complaint Root-Cause Engine

An evidence-first investigation workspace for a bank's Internal Ombudsman. It re-evaluates ticket text, surfaces stable process-failure clusters, and records append-only human review decisions without overwriting the original complaint.

## Run the verified demo stack

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:4173`. The default `DATA_BACKEND=demo` runs against deterministic synthetic records while preserving the same API contracts used by Exasol.

For local development without containers:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -e ".\backend[dev]"
$env:DATA_BACKEND = "demo"
.\.venv\Scripts\uvicorn app.main:app --app-dir backend --reload

Set-Location frontend
npm install
npm run dev
```

## Exasol mode

1. Deploy `backend/sql/001_schema.sql` and `backend/sql/002_udfs.sql` to an isolated schema.
2. Copy `.env.example` to `.env` and set `DATA_BACKEND=exasol`, `EXASOL_DSN`, `EXASOL_USER`, `EXASOL_PASSWORD`, and `EXASOL_SCHEMA`.
3. Run `backend/sql/003_verify.sql`. It must confirm transactions, Python 3.12, scikit-learn import, and a sample scoring call before the environment is accepted.
4. Start the Compose stack.

Raw complaint text stays in `TICKETS`. The API returns bounded evidence excerpts, prediction lineage, and review state. Redis transports jobs only; analytical state and review history remain in Exasol.

## API

- `POST /api/v1/tickets/batch`
- `POST /api/v1/imports/csv`
- `GET /api/v1/imports/{id}`
- `GET /api/v1/pipeline/status`
- `GET /api/v1/clusters`
- `GET /api/v1/clusters/{id}`
- `GET /api/v1/review-queue`
- `POST /api/v1/tickets/{id}/reviews`
- Interactive schema: `http://localhost:8000/docs`

## Evidence boundary

The included values and records are synthetic demonstration data. Synthetic holdouts can score planted complaint/query and cluster-recovery behavior. CFPB narratives may test robustness on real US complaint writing, but they do not validate RBI-ground accuracy or complaint/query detection.
