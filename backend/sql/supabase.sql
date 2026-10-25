-- Run this in the Supabase SQL editor before setting DATA_BACKEND=supabase.
create table if not exists tickets (
  ticket_id text primary key, source_system text not null, source_ticket_id text not null,
  received_at timestamptz not null, channel text not null, branch_id text not null,
  product text not null, agent_category text not null, agent_type text not null,
  resolution text, escalated_to_io boolean not null, raw_text text not null, created_at timestamptz not null,
  unique (source_system, source_ticket_id)
);
create table if not exists insights (
  ticket_id text primary key references tickets(ticket_id), is_complaint boolean not null,
  confidence double precision not null, trigger_phrase text not null, ground_pred text not null,
  cluster_key text, amount numeric(18,2), transaction_reference text, explanation_type text not null,
  model_version text not null, processed_at timestamptz not null
);
create table if not exists clusters (
  cluster_id text primary key, cluster_key text unique not null, label text not null, ground text not null,
  product text not null, wow_growth double precision not null, first_seen date not null,
  status text not null, summary text not null, daily_counts jsonb not null default '[]'::jsonb
);
create table if not exists review_events (
  review_id text primary key, ticket_id text not null references tickets(ticket_id), actor_id text not null,
  decision text not null, reason text, corrected_type text, corrected_ground text,
  previous_prediction jsonb not null, model_version text not null, created_at timestamptz not null
);
create table if not exists pipeline_runs (
  run_id text primary key, run_type text not null, status text not null, started_at timestamptz not null,
  finished_at timestamptz, processed_count integer not null, error text
);
create table if not exists imports (
  import_id text primary key, filename text not null, status text not null, accepted integer not null,
  errors_json jsonb not null, created_at timestamptz not null
);

alter table tickets enable row level security;
alter table insights enable row level security;
alter table clusters enable row level security;
alter table review_events enable row level security;
alter table pipeline_runs enable row level security;
alter table imports enable row level security;
