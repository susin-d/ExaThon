export type ClusterStatus = 'critical' | 'watch' | 'stable'

export interface Actor {
  id: string
  name: string
  role: string
}

export interface Cluster {
  cluster_id: string
  cluster_key: string
  label: string
  ground: string
  product: string
  wow_growth: number
  first_seen: string
  status: ClusterStatus
  summary: string
  onset_note: string
  daily_counts: number[]
  rank: number
  size: number
  branch_count: number
  confidence: number
}

export interface TicketEvidence {
  ticket_id: string
  source_ticket_id: string
  received_at: string
  channel: string
  branch_id: string
  product: string
  agent_type: 'query' | 'request' | 'complaint'
  excerpt: string
  confidence: number
  trigger_phrase: string
  ground_pred: string
  model_version: string
  processed_at: string
  review_state?: 'confirm' | 'dismiss' | 'reclassify' | null
}

export interface ClusterDetail extends Cluster {
  top_branches: { branch_id: string; count: number }[]
  tickets: TicketEvidence[]
}

export interface PipelineStage {
  name: string
  value: number
  state: 'complete' | 'active' | 'waiting'
}

export interface PipelineStatus {
  backend: string
  queue_depth: number
  tickets_total: number
  tickets_scored: number
  reviews_recorded: number
  review_queue_count: number
  active_model: string
  last_successful_run: { run_type: string; finished_at: string; status: string } | null
  failed_runs: number
  freshness: string
  stages: PipelineStage[]
}

export interface EscalationGap {
  total: number
  high_confidence: number
  explanation: string
  items: Array<{
    ticket_id: string
    source_ticket_id: string
    branch_id: string
    product: string
    agent_type: string
    excerpt: string
    confidence: number
    ground_pred: string
    trigger_phrase: string
  }>
}

export interface GroundSummary {
  rank: number
  ground: string
  complaint_count: number
  confidence: number
  share: number
}

export interface AskResult {
  question: string
  answer: string
  source: string
  data: GroundSummary[] | EscalationGap | Cluster[]
}
