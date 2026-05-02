import React, { useEffect, useMemo, useState, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { aiApi } from '../lib/api'
import { useTheme } from '../lib/theme'
import { toast } from 'sonner'
import {
  BrainCircuit,
  Send,
  X,
  Clock,
  CheckCircle2,
  Activity,
  TrendingUp,
  Target,
  BarChart2,
  PieChart,
  Loader2,
  Sparkles,
  RefreshCw,
  ArrowRight,
  Inbox,
} from 'lucide-react'

type SignalStatus = 'pending' | 'approved' | 'rejected' | 'snoozed' | 'executed' | 'expired'
type SignalAction = 'BUY' | 'SELL'

interface Rationale {
  rsi?: number
  macd?: string | number
  bollinger?: string
  weight_drift_pct?: number
  [key: string]: unknown
}

interface AISignal {
  id: number
  portfolio_id: number
  portfolio_name: string | null
  symbol: string
  company_name: string | null
  market: string
  action: SignalAction
  quantity: number
  price_at_signal: number
  estimated_value: number
  confidence: number
  rationale: Rationale
  rule_summary: string
  status: SignalStatus
  generated_at: string
  decided_at: string | null
  expires_at: string | null
}

interface AuditEntry {
  id: number
  user_id: number
  event_type: string
  portfolio_id: number | null
  signal_id: number | null
  order_id: number | null
  payload: Record<string, unknown>
  created_at: string
}

const TABS: { key: SignalStatus | 'all'; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
]

export default function AITradingInbox() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const [activeTab, setActiveTab] = useState<SignalStatus | 'all'>('pending')
  const [signals, setSignals] = useState<AISignal[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [actioningId, setActioningId] = useState<number | null>(null)

  useEffect(() => {
    loadAll()
  }, [activeTab])

  const loadAll = async () => {
    setLoading(true)
    try {
      const [sigRes, auditRes] = await Promise.all([
        aiApi.listSignals(activeTab),
        aiApi.audit().catch(() => ({ data: [] })),
      ])
      setSignals(sigRes.data || [])
      setAudit((auditRes.data || []).slice(0, 10))
    } catch (err) {
      console.error(err)
      toast.error('Failed to load signals')
    } finally {
      setLoading(false)
    }
  }

  const refresh = async () => {
    try {
      const res = await aiApi.listSignals(activeTab)
      setSignals(res.data || [])
    } catch {
      // silent
    }
  }

  const handleApprove = async (signal: AISignal) => {
    setActioningId(signal.id)
    try {
      const res = await aiApi.approveSignal(signal.id)
      toast.success(res.data?.message || `Approved ${signal.action} ${signal.symbol}`)
      await loadAll()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to approve signal')
    } finally {
      setActioningId(null)
    }
  }

  const handleReject = async (signal: AISignal) => {
    setActioningId(signal.id)
    try {
      await aiApi.rejectSignal(signal.id)
      toast.success(`Rejected ${signal.action} ${signal.symbol}`)
      await loadAll()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to reject signal')
    } finally {
      setActioningId(null)
    }
  }

  const handleSnooze = async (signal: AISignal) => {
    setActioningId(signal.id)
    try {
      await aiApi.snoozeSignal(signal.id, 60)
      toast.success(`Snoozed ${signal.symbol} for 1h`)
      await loadAll()
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      toast.error(e.response?.data?.detail || 'Failed to snooze signal')
    } finally {
      setActioningId(null)
    }
  }

  const pendingCount = useMemo(
    () => signals.filter((s) => s.status === 'pending').length,
    [signals]
  )

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col lg:flex-row gap-8 items-start">
        <div className="flex-1 w-full space-y-5 min-w-0">
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm theme-text-muted font-medium mb-2">
                <Sparkles className="w-4 h-4 text-sky-500" />
                <span>AI Trading</span>
                <span className="opacity-50">/</span>
                <span className="theme-text">Inbox</span>
              </div>
              <h1 className="text-3xl font-bold tracking-tight gradient-text">
                Pending Signals
              </h1>
              <p className="theme-text-secondary text-sm mt-1.5">
                {activeTab === 'pending' && pendingCount > 0
                  ? `Sapient AI has proposed ${pendingCount} trade${pendingCount === 1 ? '' : 's'}. Review and approve.`
                  : 'Trades proposed by the Sapient AI engine.'}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={refresh}
                className="btn-secondary text-sm flex items-center gap-2 !py-2 !px-3"
                title="Refresh"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
              <div
                className={`flex items-center gap-1 p-1 rounded-xl border ${
                  isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-100 border-slate-200'
                }`}
              >
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                      activeTab === tab.key
                        ? isDark
                          ? 'bg-slate-700 text-white shadow-sm'
                          : 'bg-white text-slate-900 shadow-sm'
                        : 'theme-text-muted hover:theme-text'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Body */}
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-sky-500"></div>
            </div>
          ) : signals.length === 0 ? (
            <EmptyState isDark={isDark} status={activeTab} />
          ) : (
            <div className="space-y-4">
              {signals.map((signal) => (
                <SignalCard
                  key={signal.id}
                  signal={signal}
                  isDark={isDark}
                  busy={actioningId === signal.id}
                  onApprove={() => handleApprove(signal)}
                  onReject={() => handleReject(signal)}
                  onSnooze={() => handleSnooze(signal)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <aside className="w-full lg:w-72 shrink-0">
          <div className="card">
            <h3 className={`text-sm font-semibold uppercase tracking-wider mb-4 ${
              isDark ? 'text-slate-100' : 'text-slate-900'
            }`}>
              Recent activity
            </h3>
            {audit.length === 0 ? (
              <p className="text-xs theme-text-muted">No recent activity yet.</p>
            ) : (
              <div className={`relative border-l ml-3 space-y-5 ${
                isDark ? 'border-slate-700' : 'border-slate-200'
              }`}>
                {audit.map((entry) => (
                  <AuditItem key={entry.id} entry={entry} isDark={isDark} />
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

function EmptyState({
  isDark,
  status,
}: {
  isDark: boolean
  status: SignalStatus | 'all'
}) {
  return (
    <div className="card text-center py-12">
      <div className={`w-16 h-16 mx-auto mb-4 rounded-2xl flex items-center justify-center ${
        isDark ? 'bg-slate-800/50' : 'bg-slate-100'
      }`}>
        <Inbox className="w-8 h-8 theme-text-muted" />
      </div>
      <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
        No {status === 'all' ? '' : status} signals
      </p>
      <p className="text-sm theme-text-muted mt-1">
        Run an AI scan from one of your portfolios to generate proposals.
      </p>
      <Link to="/portfolios" className="btn-secondary inline-flex items-center gap-2 mt-4 text-sm">
        Open Portfolios
        <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  )
}

interface SignalCardProps {
  signal: AISignal
  isDark: boolean
  busy: boolean
  onApprove: () => void
  onReject: () => void
  onSnooze: () => void
}

const SignalCard: React.FC<SignalCardProps> = ({
  signal,
  isDark,
  busy,
  onApprove,
  onReject,
  onSnooze,
}) => {
  const isBuy = signal.action === 'BUY'
  const accent = isBuy ? 'bg-emerald-500' : 'bg-red-500'
  const accentGlow = isBuy
    ? 'shadow-[0_0_10px_rgba(16,185,129,0.5)]'
    : 'shadow-[0_0_10px_rgba(239,68,68,0.5)]'

  const isPending = signal.status === 'pending'

  const generated = new Date(signal.generated_at)
  const minsAgo = Math.max(0, Math.round((Date.now() - generated.getTime()) / 60000))
  const ago =
    minsAgo < 1 ? 'just now' : minsAgo < 60 ? `${minsAgo} min ago` : `${Math.round(minsAgo / 60)}h ago`

  const reasons = buildReasons(signal)

  return (
    <div className="card relative overflow-hidden">
      <div className={`absolute top-0 bottom-0 left-0 w-1.5 ${accent} ${accentGlow}`} />

      {/* Top row */}
      <div className="flex flex-wrap md:flex-nowrap justify-between items-start gap-3 mb-4 pl-2">
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`badge px-3 py-1 font-bold tracking-wide ${
              isBuy
                ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                : 'bg-red-500/10 text-red-500 border-red-500/20'
            }`}
          >
            {signal.action}
          </span>
          <div className="flex items-baseline gap-2">
            <h3 className={`text-lg font-bold tracking-tight ${
              isDark ? 'text-slate-100' : 'text-slate-900'
            }`}>
              {signal.symbol}
            </h3>
            {signal.company_name && (
              <span className="theme-text-muted text-sm">· {signal.company_name}</span>
            )}
          </div>
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
              isDark
                ? 'bg-slate-800 text-slate-300 border-slate-700'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}
          >
            {signal.market}
          </span>
          {signal.portfolio_name && (
            <Link
              to={`/portfolios/${signal.portfolio_id}`}
              className="text-xs text-sky-500 hover:text-sky-600 transition-colors"
            >
              {signal.portfolio_name}
            </Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs theme-text-muted font-medium flex items-center gap-1">
            <Clock className="w-3 h-3" /> {ago}
          </span>
          <span className="badge badge-sky flex items-center gap-1.5">
            <BrainCircuit className="w-3.5 h-3.5" />
            {Math.round((signal.confidence || 0) * 100)}%
          </span>
        </div>
      </div>

      {/* Middle */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-10 mb-5 pl-2">
        <div className="space-y-3">
          <h4 className="text-xs uppercase tracking-wider theme-text-muted font-semibold mb-2">
            Trade plan
          </h4>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Quantity" value={`${formatNumber(signal.quantity)} shares`} />
            <Field label="Order Type" value="Market" />
            <Field label="Price at signal" value={fmtCcy(signal.price_at_signal, signal.market)} />
            <Field
              label={isBuy ? 'Estimated Cost' : 'Estimated Value'}
              value={`~${fmtCcy(signal.estimated_value, signal.market)}`}
            />
          </div>
          {signal.rationale?.weight_drift_pct !== undefined && (
            <div className={`mt-3 pt-3 border-t flex items-center justify-between ${
              isDark ? 'border-slate-700/50' : 'border-slate-200'
            }`}>
              <span className="text-xs theme-text-muted flex items-center gap-1.5">
                <PieChart className="w-3.5 h-3.5" /> Weight drift
              </span>
              <span
                className={`text-sm font-medium ${
                  Number(signal.rationale.weight_drift_pct) >= 0
                    ? 'text-emerald-500'
                    : 'text-red-500'
                }`}
              >
                {Number(signal.rationale.weight_drift_pct) >= 0 ? '+' : ''}
                {Number(signal.rationale.weight_drift_pct).toFixed(2)}%
              </span>
            </div>
          )}
        </div>

        <div>
          <h4 className="text-xs uppercase tracking-wider theme-text-muted font-semibold mb-3">
            Why Sapient is proposing this
          </h4>
          <ul className="space-y-2.5">
            {reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm theme-text-secondary">
                <r.icon className="w-4 h-4 text-sky-500 shrink-0 mt-0.5" />
                <span>{r.text}</span>
              </li>
            ))}
            {signal.rule_summary && (
              <li className="flex items-start gap-2.5 text-sm theme-text-secondary">
                <Activity className="w-4 h-4 text-sky-500 shrink-0 mt-0.5" />
                <span>{signal.rule_summary}</span>
              </li>
            )}
          </ul>
        </div>
      </div>

      {/* Bottom */}
      <div className={`flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pt-4 border-t pl-2 ${
        isDark ? 'border-slate-700/50' : 'border-slate-200'
      }`}>
        <span className="text-xs theme-text-muted">
          Status: <span className="font-medium theme-text">{signal.status}</span>
          {signal.decided_at && ` · decided ${new Date(signal.decided_at).toLocaleString()}`}
        </span>
        {isPending ? (
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              onClick={onSnooze}
              disabled={busy}
              className="btn-secondary text-xs !py-2 !px-3"
            >
              Snooze 1h
            </button>
            <button
              onClick={onReject}
              disabled={busy}
              className={`text-sm font-medium rounded-xl px-4 py-2 border transition-colors flex items-center gap-1.5 ${
                isDark
                  ? 'border-red-500/30 text-red-400 hover:bg-red-500/10'
                  : 'border-red-200 text-red-500 hover:bg-red-50'
              }`}
            >
              <X className="w-4 h-4" />
              Reject
            </button>
            <button
              onClick={onApprove}
              disabled={busy}
              className="btn-success flex items-center gap-2 !py-2 text-sm flex-1 sm:flex-none justify-center"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Approve & send
            </button>
          </div>
        ) : (
          <span className="text-xs theme-text-muted">No further actions available.</span>
        )}
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="block text-xs theme-text-muted mb-0.5">{label}</span>
      <span className="text-sm font-semibold theme-text">{value}</span>
    </div>
  )
}

function buildReasons(signal: AISignal): { icon: typeof BarChart2; text: ReactNode }[] {
  const r = signal.rationale || {}
  const out: { icon: typeof BarChart2; text: ReactNode }[] = []
  if (typeof r.rsi === 'number') {
    out.push({
      icon: BarChart2,
      text: (
        <>
          <span className="font-semibold theme-text">RSI {r.rsi.toFixed(1)}</span>
          {' '}({signal.action === 'BUY' ? 'oversold' : 'overbought'})
        </>
      ),
    })
  }
  if (r.macd) {
    out.push({
      icon: TrendingUp,
      text: (
        <>
          <span className="font-semibold theme-text">MACD</span> {String(r.macd)}
        </>
      ),
    })
  }
  if (r.bollinger) {
    out.push({
      icon: Target,
      text: (
        <>
          <span className="font-semibold theme-text">Bollinger</span> {String(r.bollinger)}
        </>
      ),
    })
  }
  return out
}

interface AuditItemProps {
  entry: AuditEntry
  isDark: boolean
}

const AuditItem: React.FC<AuditItemProps> = ({ entry, isDark }) => {
  const tone = toneForEvent(entry.event_type)
  const Icon = tone.icon
  return (
    <div className="relative pl-6">
      <div
        className={`absolute -left-[11px] top-1 rounded-full p-1 border ${tone.border} ${
          isDark ? 'bg-slate-900' : 'bg-white'
        }`}
      >
        <Icon className={`w-3 h-3 ${tone.color}`} />
      </div>
      <p className={`text-sm leading-snug ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
        {humanizeEvent(entry)}
      </p>
      <span className="text-xs theme-text-muted mt-1 block">
        {new Date(entry.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
    </div>
  )
}

function toneForEvent(event: string) {
  if (event.includes('approve') || event.includes('execute')) {
    return { icon: CheckCircle2, color: 'text-emerald-500', border: 'border-emerald-500/40' }
  }
  if (event.includes('reject') || event.includes('cancel') || event.includes('kill')) {
    return { icon: X, color: 'text-red-500', border: 'border-red-500/40' }
  }
  return { icon: BrainCircuit, color: 'text-sky-500', border: 'border-sky-500/40' }
}

function humanizeEvent(entry: AuditEntry): string {
  const payload = entry.payload || {}
  const symbol = (payload.symbol as string) || ''
  const action = (payload.action as string) || ''
  const qty = payload.quantity as number | undefined
  const detail = [action, qty ? `${qty}` : '', symbol].filter(Boolean).join(' ')
  switch (entry.event_type) {
    case 'signal.approved':
      return `Approved ${detail || 'signal'}`
    case 'signal.rejected':
      return `Rejected ${detail || 'signal'}`
    case 'signal.snoozed':
      return `Snoozed ${detail || 'signal'}`
    case 'signal.executed':
      return `Executed ${detail || 'signal'}`
    case 'signal.created':
      return `New signal ${detail || ''}`
    case 'kill_switch.triggered':
      return 'Kill switch triggered'
    case 'order.placed':
      return `Order placed ${detail}`
    case 'settings.updated':
      return 'AI settings updated'
    default:
      return entry.event_type.replace(/[._]/g, ' ')
  }
}

function formatNumber(n: number): string {
  if (n === undefined || n === null || isNaN(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function fmtCcy(n: number, market: string): string {
  if (n === undefined || n === null || isNaN(n)) return '—'
  const sym = market === 'ASX' ? 'A$' : market === 'NASDAQ' || market === 'NYSE' ? 'US$' : '$'
  return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
