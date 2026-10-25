import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  FileSearch,
  Filter,
  ListChecks,
  LoaderCircle,
  Menu,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldAlert,
  Table2,
  Upload,
  X,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useActor } from './actor-context'
import { api } from './api'
import type { AskResult, Cluster, ClusterDetail, ClusterStatus, EscalationGap, GroundSummary, PipelineStatus, TicketEvidence } from './types'

type View = 'causes' | 'review' | 'escalation' | 'grounds' | 'ask' | 'pipeline'
type Notice = { tone: 'success' | 'error' | 'info'; text: string }

const number = new Intl.NumberFormat('en-IN')
const date = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

function formatDate(value: string) {
  return date.format(new Date(value))
}

function confidence(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatRelative(value: string) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60_000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return `${hours} hr${hours === 1 ? '' : 's'} ago`
}

function App() {
  const actor = useActor()
  const [view, setView] = useState<View>('causes')
  const [clusters, setClusters] = useState<Cluster[]>([])
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null)
  const [selected, setSelected] = useState<ClusterDetail | null>(null)
  const [reviewQueue, setReviewQueue] = useState<TicketEvidence[]>([])
  const [escalationGap, setEscalationGap] = useState<EscalationGap | null>(null)
  const [grounds, setGrounds] = useState<GroundSummary[]>([])
  const [askResult, setAskResult] = useState<AskResult | null>(null)
  const [askQuestion, setAskQuestion] = useState('')
  const [askLoading, setAskLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [search, setSearch] = useState('')
  const [product, setProduct] = useState('')
  const [mobileNav, setMobileNav] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  const fileInput = useRef<HTMLInputElement>(null)
  const drawerReturnFocus = useRef<HTMLElement | null>(null)
  const closeDrawer = useCallback(() => setSelected(null), [])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const update = () => setIsMobile(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  const loadCore = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [clusterData, pipelineData] = await Promise.all([api.clusters(search, product), api.pipeline()])
      setClusters(clusterData)
      setPipeline(pipelineData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The investigation service could not be reached.')
    } finally {
      setLoading(false)
    }
  }, [search, product])

  useEffect(() => {
    const timeout = window.setTimeout(loadCore, search ? 250 : 0)
    return () => window.clearTimeout(timeout)
  }, [loadCore, search])

  useEffect(() => {
    if (view === 'review') {
      api.reviewQueue().then(setReviewQueue).catch((err: Error) => setError(err.message))
    }
    if (view === 'escalation') api.escalationGap().then(setEscalationGap).catch((err: Error) => setError(err.message))
    if (view === 'grounds') api.topGrounds().then(setGrounds).catch((err: Error) => setError(err.message))
  }, [view])

  const ask = async () => {
    if (!askQuestion.trim()) return
    setAskLoading(true)
    try {
      setAskResult(await api.ask(askQuestion.trim()))
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'The question could not be answered.' })
    } finally {
      setAskLoading(false)
    }
  }

  const openCluster = async (clusterId: string) => {
    try {
      drawerReturnFocus.current = document.activeElement as HTMLElement
      setSelected(await api.cluster(clusterId))
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Could not load cluster evidence.' })
    }
  }

  const importCsv = async (file?: File) => {
    if (!file) return
    setNotice({ tone: 'info', text: `Validating ${file.name}…` })
    try {
      const result = await api.importCsv(file)
      setNotice({
        tone: result.error_count ? 'info' : 'success',
        text: `${result.accepted} tickets accepted; ${result.error_count} row errors recorded.`,
      })
      await loadCore()
    } catch (err) {
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'The CSV import failed.' })
    }
  }

  const navigate = (next: View) => {
    setView(next)
    setSelected(null)
    setMobileNav(false)
  }

  return (
    <div className="app-shell">
      <Sidebar view={view} navigate={navigate} actor={actor} open={mobileNav} reviewCount={pipeline?.review_queue_count ?? null} isMobile={isMobile} />
      <main className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label={mobileNav ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileNav} onClick={() => setMobileNav(!mobileNav)}>
            <Menu size={20} />
          </button>
          <div className="topbar-title">
            <span className="bank-mark" aria-hidden="true">BCB</span>
            <div>
              <strong>Bharat Co-operative Bank</strong>
              <span>Synthetic demonstration environment</span>
            </div>
          </div>
          <div className="topbar-actions">
            <span className={`freshness ${pipeline?.freshness === 'current' ? 'is-current' : ''}`}>
              <span className="status-dot" />
              {pipeline?.freshness === 'current' ? 'Evidence current' : 'Processing updates'}
            </span>
            <input ref={fileInput} type="file" accept=".csv,text/csv" hidden onChange={(event) => importCsv(event.target.files?.[0])} />
            <button className="button secondary" aria-label="Import tickets from CSV" title="Import tickets from CSV" onClick={() => fileInput.current?.click()}>
              <Upload size={17} /> <span>Import tickets</span>
            </button>
          </div>
        </header>

        {pipeline && <EvidenceChain status={pipeline} />}
        {notice && <Notice notice={notice} dismiss={() => setNotice(null)} />}

        <section className="page-frame">
          {error ? (
            <ErrorState message={error} retry={loadCore} />
          ) : view === 'causes' ? (
            <RootCauseBoard
              clusters={clusters}
              loading={loading}
              search={search}
              setSearch={setSearch}
              product={product}
              setProduct={setProduct}
              onOpen={openCluster}
              refresh={loadCore}
            />
          ) : view === 'review' ? (
            <ReviewQueue
              tickets={reviewQueue}
              onReviewed={async (ticket, decision, reason) => {
                await api.review(ticket.ticket_id, {
                  decision,
                  reason,
                  corrected_type: decision === 'reclassify' ? 'complaint' : undefined,
                })
                setReviewQueue(await api.reviewQueue())
                setNotice({ tone: 'success', text: `Decision recorded for ${ticket.source_ticket_id}. Raw ticket unchanged.` })
              }}
            />
          ) : view === 'escalation' ? (
            <EscalationGapView data={escalationGap} />
          ) : view === 'grounds' ? (
            <GroundsView grounds={grounds} />
          ) : view === 'ask' ? (
            <AskDataView question={askQuestion} setQuestion={setAskQuestion} result={askResult} loading={askLoading} ask={ask} />
          ) : (
            <PipelineView status={pipeline} />
          )}
        </section>
      </main>
      {selected && <EvidenceDrawer cluster={selected} close={closeDrawer} returnFocus={drawerReturnFocus} />}
    </div>
  )
}

function Sidebar({ view, navigate, actor, open, reviewCount, isMobile }: { view: View; navigate: (view: View) => void; actor: ReturnType<typeof useActor>; open: boolean; reviewCount: number | null; isMobile: boolean }) {
  const items = [
    { id: 'causes' as const, label: 'Root causes', icon: FileSearch, count: null },
    { id: 'review' as const, label: 'Review queue', icon: ListChecks, count: reviewCount },
    { id: 'escalation' as const, label: 'Escalation gap', icon: ShieldAlert, count: null },
    { id: 'grounds' as const, label: 'Top five grounds', icon: Table2, count: null },
    { id: 'ask' as const, label: 'Ask the data', icon: MessageSquareText, count: null },
    { id: 'pipeline' as const, label: 'Pipeline', icon: CircleGauge, count: null },
  ]
  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-hidden={isMobile && !open} inert={isMobile && !open ? true : undefined}>
      <div className="brand">
        <div className="brand-symbol" aria-hidden="true"><span /><span /><span /></div>
        <div><strong>Complaint</strong><span>Root-Cause Engine</span></div>
      </div>
      <nav aria-label="Primary navigation">
        {items.map(({ id, label, icon: Icon, count }) => (
          <button key={id} className={view === id ? 'active' : ''} onClick={() => navigate(id)} aria-current={view === id ? 'page' : undefined}>
            <Icon size={19} strokeWidth={1.8} />
            <span>{label}</span>
            {count !== null && <b>{count > 999 ? '999+' : count}</b>}
          </button>
        ))}
      </nav>
      <div className="sidebar-context">
        <ShieldCheck size={18} />
        <div><strong>Private workspace</strong><span>Single-bank demo boundary</span></div>
      </div>
      <div className="actor">
        <span className="avatar">AR</span>
        <div><strong>{actor.name}</strong><span>{actor.role}</span></div>
      </div>
    </aside>
  )
}

function EvidenceChain({ status }: { status: PipelineStatus }) {
  return (
    <section className="evidence-chain" aria-label="Evidence processing status">
      <div className="chain-heading">
        <span>Evidence chain</span>
        <strong>{status.active_model}</strong>
      </div>
      <ol>
        {status.stages.map((stage, index) => (
          <li key={stage.name} className={stage.state}>
            <span className="chain-node">{stage.state === 'complete' ? <Check size={13} /> : index + 1}</span>
            <div><strong>{stage.name}</strong><span>{number.format(stage.value)} records</span></div>
          </li>
        ))}
      </ol>
      <div className="chain-refresh"><Clock3 size={15} /><span>Evidence {status.freshness}</span><strong>Cluster refresh · {status.last_successful_run ? formatRelative(status.last_successful_run.finished_at) : 'not run'}</strong></div>
    </section>
  )
}

function RootCauseBoard(props: {
  clusters: Cluster[]
  loading: boolean
  search: string
  setSearch: (value: string) => void
  product: string
  setProduct: (value: string) => void
  onOpen: (id: string) => void
  refresh: () => void
}) {
  const products = ['Payments', 'Loans', 'Cards', 'Deposits']
  return (
    <div className="board-layout">
      <div className="page-heading">
        <div>
          <h1>What is driving complaints now?</h1>
          <p>Ranked from customer language, not the category selected when the ticket was logged.</p>
        </div>
        <button className="icon-button" aria-label="Refresh root causes" title="Refresh root causes" onClick={props.refresh}>
          <RefreshCw size={18} />
        </button>
      </div>
      <div className="filters" role="search">
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Search root causes</span>
          <input value={props.search} onChange={(e) => props.setSearch(e.target.value)} placeholder="Search cause or RBI ground" />
        </label>
        <label className="select-field">
          <Filter size={16} />
          <span className="sr-only">Filter by product</span>
          <select value={props.product} onChange={(e) => props.setProduct(e.target.value)}>
            <option value="">All products</option>
            {products.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <span className="result-count">{props.clusters.length} active causes</span>
      </div>
      <div className="table-wrap">
        <table className="cluster-table">
          <thead><tr><th>Rank</th><th>Root cause</th><th>RBI ground</th><th>Volume</th><th>7-day change</th><th>Evidence</th><th><span className="sr-only">Open</span></th></tr></thead>
          <tbody>
            {props.loading ? <LoadingRows /> : props.clusters.map((cluster) => (
              <tr key={cluster.cluster_id} onClick={() => props.onOpen(cluster.cluster_id)}>
                <td><span className={`rank rank-${cluster.rank}`}>{cluster.rank}</span></td>
                <td className="cause-cell">
                  <button onClick={() => props.onOpen(cluster.cluster_id)}>{cluster.label}</button>
                  <span><StatusLabel status={cluster.status} /> First seen {formatDate(cluster.first_seen)}</span>
                </td>
                <td>{cluster.ground}</td>
                <td><strong className="tabular">{number.format(cluster.size)}</strong><span>{cluster.branch_count} branches</span></td>
                <td><Growth value={cluster.wow_growth} /></td>
                <td><strong className="tabular">{confidence(cluster.confidence)}</strong><span>mean confidence</span></td>
                <td><ChevronRight size={18} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!props.loading && props.clusters.length === 0 && (
          <div className="empty-state"><Search size={24} /><strong>No causes match these filters</strong><span>Clear the search or choose another product.</span></div>
        )}
      </div>
      <div className="mobile-cluster-list" aria-label="Root-cause summaries">
        {props.clusters.map((cluster) => (
          <button key={cluster.cluster_id} onClick={() => props.onOpen(cluster.cluster_id)}>
            <span className={`rank rank-${cluster.rank}`}>{cluster.rank}</span>
            <span className="mobile-cause-copy">
              <strong>{cluster.label}</strong>
              <StatusLabel status={cluster.status} />
              <small>{cluster.ground}</small>
            </span>
            <span className="mobile-cause-metrics">
              <b>{cluster.size}</b><small>tickets</small>
              <b className={cluster.wow_growth > 0 ? 'danger-text' : ''}>{cluster.wow_growth > 0 ? '+' : ''}{cluster.wow_growth}%</b><small>7-day</small>
              <b>{confidence(cluster.confidence)}</b><small>confidence</small>
            </span>
            <ChevronRight size={18} />
          </button>
        ))}
      </div>
      <div className="board-footnote"><Database size={15} /><span>Illustrative values from synthetic Bharat Co-operative Bank data. They are not production performance claims.</span></div>
    </div>
  )
}

function StatusLabel({ status }: { status: ClusterStatus }) {
  return <span className={`status-label ${status}`}><span />{status === 'critical' ? 'Immediate review' : status === 'watch' ? 'Watch closely' : 'Stable'}</span>
}

function Growth({ value }: { value: number }) {
  const positive = value >= 0
  return <span className={`growth ${positive ? 'rising' : 'falling'}`}>{positive ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}<strong>{Math.abs(value).toFixed(1)}%</strong><span>vs last week</span></span>
}

function LoadingRows() {
  return <>{[1, 2, 3, 4].map((row) => <tr className="loading-row" key={row}><td colSpan={7}><span /></td></tr>)}</>
}

function EvidenceDrawer({ cluster, close, returnFocus }: { cluster: ClusterDetail; close: () => void; returnFocus: { current: HTMLElement | null } }) {
  const closeButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const focusReturnTarget = returnFocus.current
    closeButton.current?.focus()
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('keydown', handleKey)
      focusReturnTarget?.focus()
    }
  }, [close, returnFocus])
  return (
    <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="cluster-title">
      <div className="drawer-header">
        <div><h2 id="cluster-title">{cluster.label}</h2><div className="drawer-state"><StatusLabel status={cluster.status} /><span>First seen {formatDate(cluster.first_seen)}</span></div><p>{cluster.summary}</p></div>
        <button ref={closeButton} className="icon-button" aria-label="Close evidence panel" onClick={close}><X size={20} /></button>
      </div>
      <div className="drawer-stats">
        <div><span>Matched tickets</span><strong>{number.format(cluster.size)}</strong></div>
        <div><span>Branches</span><strong>{cluster.branch_count}</strong></div>
        <div><span>7-day change</span><strong className={cluster.wow_growth > 0 ? 'danger-text' : ''}>{cluster.wow_growth > 0 ? '+' : ''}{cluster.wow_growth}%</strong></div>
      </div>
      <section className="timeline-section">
        <div className="section-heading"><h3>Daily onset</h3><span>Last 7 days</span></div>
        <div className="timeline-bars" aria-label={`Daily complaint counts: ${cluster.daily_counts.join(', ')}`}>
          {cluster.daily_counts.map((count, index) => <div key={index}><span style={{ height: `${Math.max(12, count / Math.max(...cluster.daily_counts) * 100)}%` }} /><b>{count}</b></div>)}
        </div>
        <p className="onset-note"><AlertTriangle size={15} />{cluster.onset_note}</p>
      </section>
      <section>
        <div className="section-heading"><h3>Branch concentration</h3><span>{cluster.top_branches.length} shown</span></div>
        <div className="branch-list">
          {cluster.top_branches.map((branch, index) => <div key={branch.branch_id}><span>{index + 1}</span><strong>{branch.branch_id}</strong><div><i style={{ width: `${Math.max(14, branch.count / Math.max(...cluster.top_branches.map((b) => b.count)) * 100)}%` }} /></div><b>{branch.count}</b></div>)}
        </div>
      </section>
      <section className="ticket-evidence">
        <div className="section-heading"><h3>Supporting tickets</h3><span>Highest confidence first</span></div>
        {cluster.tickets.map((ticket) => <EvidenceTicket ticket={ticket} key={ticket.ticket_id} />)}
      </section>
    </aside>
  )
}

function EvidenceTicket({ ticket }: { ticket: TicketEvidence }) {
  const parts = ticket.excerpt.split(new RegExp(`(${ticket.trigger_phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig'))
  return (
    <article className="evidence-ticket">
      <div><strong>{ticket.source_ticket_id}</strong><span>{ticket.branch_id} · {ticket.channel.replace('_', ' ')}</span><b>{confidence(ticket.confidence)}</b></div>
      <p>{parts.map((part, index) => part.toLowerCase() === ticket.trigger_phrase.toLowerCase() ? <mark key={index}>{part}</mark> : part)}</p>
      <footer><span>Agent: {ticket.agent_type}</span><span>Model: complaint</span><span>{ticket.model_version}</span></footer>
    </article>
  )
}

function EscalationGapView({ data }: { data: EscalationGap | null }) {
  return (
    <div>
      <div className="page-heading"><div><h1>Escalation gap</h1><p>Complaint-like tickets that appear unresolved but never reached the Internal Ombudsman.</p></div><span className="queue-total">{data?.total ?? '—'} candidates</span></div>
      {!data ? <div className="empty-state large"><LoaderCircle className="spin" size={28} /><strong>Loading escalation evidence</strong></div> : (
        <>
          <div className="drawer-stats"><div><span>Needs escalation review</span><strong>{number.format(data.total)}</strong></div><div><span>High confidence</span><strong>{number.format(data.high_confidence)}</strong></div></div>
          <p className="onset-note"><ShieldAlert size={15} />{data.explanation}</p>
          <div className="review-list escalation-list">{data.items.map((item) => <article className="evidence-ticket" key={item.ticket_id}><div><strong>{item.source_ticket_id}</strong><span>{item.branch_id} · {item.product}</span><b>{confidence(item.confidence)}</b></div><p>{item.excerpt}</p><footer><span>{item.ground_pred}</span><span>Trigger: {item.trigger_phrase}</span><span>Agent: {item.agent_type}</span></footer></article>)}</div>
        </>
      )}
    </div>
  )
}

function GroundsView({ grounds }: { grounds: GroundSummary[] }) {
  return (
    <div>
      <div className="page-heading"><div><h1>Top five complaint grounds</h1><p>Disclosure-ready ranking generated from customer language rather than agent labels.</p></div></div>
      {!grounds.length ? <div className="empty-state large"><LoaderCircle className="spin" size={28} /><strong>Loading ground analysis</strong></div> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Rank</th><th>RBI ground</th><th>Complaints</th><th>Share</th><th>Confidence</th></tr></thead><tbody>{grounds.map((ground) => <tr key={ground.ground}><td><strong>#{ground.rank}</strong></td><td>{ground.ground}</td><td>{number.format(ground.complaint_count)}</td><td>{Math.round(ground.share * 100)}%</td><td>{confidence(ground.confidence)}</td></tr>)}</tbody></table></div>}
    </div>
  )
}

function AskDataView({ question, setQuestion, result, loading, ask }: { question: string; setQuestion: (value: string) => void; result: AskResult | null; loading: boolean; ask: () => void }) {
  return (
    <div>
      <div className="page-heading"><div><h1>Ask the data</h1><p>Read-only questions grounded in the evidence tables. Try a suggested question or write your own.</p></div></div>
      <div className="ask-panel"><div className="ask-input"><MessageSquareText size={19} /><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && ask()} placeholder="Which branches drove the ATM cluster?" /><button className="button confirm" onClick={ask} disabled={loading || !question.trim()}>{loading ? <LoaderCircle className="spin" size={16} /> : 'Ask'}</button></div><div className="ask-suggestions"><button onClick={() => setQuestion('What are the top five complaint grounds?')}>Top five grounds</button><button onClick={() => setQuestion('Which complaints never reached the ombudsman?')}>Escalation gaps</button><button onClick={() => setQuestion('Which branches drove the ATM cluster?')}>ATM branches</button></div></div>
      {result && <section className="ask-result"><div className="section-heading"><h2>Answer</h2><span>Source: {result.source}</span></div><p>{result.answer}</p><pre>{JSON.stringify(result.data, null, 2)}</pre></section>}
    </div>
  )
}

function ReviewQueue({ tickets, onReviewed }: { tickets: TicketEvidence[]; onReviewed: (ticket: TicketEvidence, decision: 'confirm' | 'dismiss' | 'reclassify', reason?: string) => Promise<void> }) {
  const [activeTicketId, setActiveTicketId] = useState<string | null>(tickets[0]?.ticket_id ?? null)
  const active = tickets.find((ticket) => ticket.ticket_id === activeTicketId) ?? tickets[0] ?? null
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])

  const decide = async (decision: 'confirm' | 'dismiss' | 'reclassify') => {
    if (!active || (decision !== 'confirm' && !reason.trim())) return
    setSaving(true)
    try {
      await onReviewed(active, decision, reason.trim() || undefined)
      setActiveTicketId(null)
      setReason('')
    } finally { setSaving(false) }
  }

  return (
    <div>
      <div className="page-heading"><div><h1>Misclassification review</h1><p>Recall-first candidates where customer language conflicts with the agent-entered type.</p></div><span className="queue-total">{tickets.length} awaiting review</span></div>
      {tickets.length === 0 ? <div className="empty-state large"><Check size={28} /><strong>The review queue is clear</strong><span>New candidates will appear after scoring.</span></div> : (
        <div className="review-layout">
          <div className="review-list" role="listbox" aria-label="Tickets awaiting review">
            {tickets.map((ticket, index) => <button ref={(node) => { optionRefs.current[index] = node }} role="option" aria-selected={active?.ticket_id === ticket.ticket_id} key={ticket.ticket_id} className={active?.ticket_id === ticket.ticket_id ? 'active' : ''} onClick={() => setActiveTicketId(ticket.ticket_id)} onKeyDown={(event) => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); const next = event.key === 'ArrowDown' ? Math.min(tickets.length - 1, index + 1) : Math.max(0, index - 1); setActiveTicketId(tickets[next].ticket_id); optionRefs.current[next]?.focus() } }}><div><strong>{ticket.source_ticket_id}</strong><span>{ticket.product} · {ticket.branch_id}</span></div><b>{confidence(ticket.confidence)}</b><p>{ticket.excerpt}</p><span className="trigger">“{ticket.trigger_phrase}”</span></button>)}
          </div>
          {active && <section className="review-workbench">
            <div className="review-title"><h2>Review {active.source_ticket_id}: does this text describe a complaint?</h2><span className="confidence-block"><strong>{confidence(active.confidence)}</strong> model confidence</span></div>
            <blockquote>{active.excerpt}</blockquote>
            <div className="classification-compare"><div><span>Agent entered</span><strong>{active.agent_type}</strong></div><ChevronRight size={20} /><div><span>Model suggests</span><strong>Complaint</strong><small>{active.ground_pred}</small></div></div>
            <div className="model-evidence"><FileSearch size={18} /><div><strong>Why it was flagged</strong><p>The phrase <mark>{active.trigger_phrase}</mark> contributed to this prediction. This is model evidence, not a confirmed fact.</p></div></div>
            <label className="reason-field"><span>Reason for dismissing or reclassifying</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Record the evidence behind your correction" rows={3} /></label>
            <div className="decision-actions">
              <button className="button confirm" disabled={saving} onClick={() => decide('confirm')}><Check size={17} />Confirm complaint</button>
              <button className="button secondary" disabled={saving || !reason.trim()} onClick={() => decide('reclassify')}><RefreshCw size={16} />Reclassify</button>
              <button className="button quiet-danger" disabled={saving || !reason.trim()} onClick={() => decide('dismiss')}><XCircle size={16} />Dismiss finding</button>
              {saving && <LoaderCircle className="spin" size={18} />}
            </div>
          </section>}
        </div>
      )}
    </div>
  )
}

function PipelineView({ status }: { status: PipelineStatus | null }) {
  if (!status) return null
  return <div><div className="page-heading"><div><h1>Pipeline and model lineage</h1><p>Operational status for ingestion, scoring, discovery, and human review.</p></div><span className={`backend-badge ${status.backend}`}>{status.backend} backend</span></div><div className="pipeline-grid"><section className="pipeline-table"><h2>Current run state</h2><dl><div><dt>Queued scoring jobs</dt><dd>{status.queue_depth}</dd></div><div><dt>Tickets received</dt><dd>{number.format(status.tickets_total)}</dd></div><div><dt>Tickets scored</dt><dd>{number.format(status.tickets_scored)}</dd></div><div><dt>Review events</dt><dd>{number.format(status.reviews_recorded)}</dd></div><div><dt>Failed runs</dt><dd className={status.failed_runs ? 'danger-text' : ''}>{status.failed_runs}</dd></div></dl></section><section className="lineage"><h2>Active analytical version</h2><div className="version-mark"><Database size={22} /><div><strong>{status.active_model}</strong><span>Recall-first hybrid · threshold 0.65</span></div></div><p>Every prediction and human decision stores this version. Reprocessing creates new lineage without changing the raw ticket.</p><div className="lineage-note"><ShieldCheck size={17} /><span>Demo values are synthetic and explicitly separated from production evidence.</span></div></section></div></div>
}

function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <div className="error-state"><XCircle size={28} /><h1>The evidence service is unavailable</h1><p>{message}</p><button className="button primary" onClick={retry}><RefreshCw size={17} />Try again</button></div>
}

function Notice({ notice, dismiss }: { notice: Notice; dismiss: () => void }) {
  return <div className={`notice ${notice.tone}`} role="status"><span>{notice.text}</span><button aria-label="Dismiss notification" onClick={dismiss}><X size={16} /></button></div>
}

export default App
