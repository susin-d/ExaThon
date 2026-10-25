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

## Deploy both services

Deploy the backend as a Docker web service on Render using the included
[render.yaml](./render.yaml). Set `DATA_BACKEND=demo` for a self-contained demo, or
set `DATA_BACKEND=supabase` and provide `SUPABASE_DB_URL` for persistent production
data. Keep `QUEUE_ENABLED=false` to run without Redis.

Deploy the frontend as a Vercel project with `frontend/` as its root directory. Set
`VITE_API_URL` to the deployed backend URL, for example:

```text
VITE_API_URL=https://complaint-root-cause-api.onrender.com
```

The included [frontend/vercel.json](./frontend/vercel.json) is only needed when Redis
processing is enabled; it can be removed or left unused in no-Redis mode.

## Exasol mode

1. Deploy `backend/sql/001_schema.sql` and `backend/sql/002_udfs.sql` to an isolated schema.
2. Copy `.env.example` to `.env` and set `DATA_BACKEND=exasol`, `EXASOL_DSN`, `EXASOL_USER`, `EXASOL_PASSWORD`, and `EXASOL_SCHEMA`.
3. Run `backend/sql/003_verify.sql`. It must confirm transactions, Python 3.12, scikit-learn import, and a sample scoring call before the environment is accepted.
4. Start the Compose stack.

## Supabase without Redis

For a serverless-friendly deployment, run `backend/sql/supabase.sql` in the Supabase SQL
editor and set `DATA_BACKEND=supabase` plus `SUPABASE_DB_URL` to the Supabase **direct
connection or pooler URL**. Keep the database URL server-side; never expose it as a
`VITE_` variable.

Redis is optional. Set `QUEUE_ENABLED=false` (the default) and leave `REDIS_URL` empty.
The API scores newly ingested tickets synchronously, so the backend works with only
Supabase and does not require a Redis service, worker process, or cron job.

If asynchronous processing is needed later, set `QUEUE_ENABLED=true`, provide a managed
Redis URL such as Upstash Redis, and use `POST /internal/cron/worker`. It processes at
most `WORKER_BATCH_SIZE` Redis jobs per request and requires `Authorization: Bearer
$CRON_SECRET`.

When asynchronous Redis processing is enabled and the frontend is deployed to Vercel
with `frontend/` as the project root, the included `frontend/vercel.json` schedules
`/api/cron/worker` every minute. Set these Vercel environment variables:

- `VITE_API_URL`: public backend URL used by the browser
- `BACKEND_URL`: same backend URL, used only by the optional server-side cron bridge
- `CRON_SECRET`: the same random value configured on the backend

Raw complaint text stays in `TICKETS`. The API returns bounded evidence excerpts, prediction lineage, and review state. Analytical state and review history remain in Supabase.

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

## Validation and scale interfaces

- `GET /api/v1/grounds/catalog` returns the versioned demo RBI-ground catalog.
- `GET /api/v1/validation/status` reports configured validation assets.
- `POST /api/v1/validation/accuracy` accepts CSV with `text,true_type` columns and
  returns accuracy and complaint recall. Third-party CFPB data is not bundled; upload
  the public dataset after mapping its labels.
- `DEMO_SCALE` multiplies deterministic generated demo tickets for controlled local
  scale tests. Keep it at `1` for serverless demos.

The included values and records are synthetic demonstration data. Synthetic holdouts can score planted complaint/query and cluster-recovery behavior. CFPB narratives may test robustness on real US complaint writing, but they do not validate RBI-ground accuracy or complaint/query detection.

## License

This project is licensed under the [MIT License](LICENSE).

