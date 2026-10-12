import { useEffect, useState } from 'react'
import FactorStrategy from '../components/FactorStrategy'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { portfolioApi, stocksApi, brokerApi, aiApi, factorsApi, apiErrorMessage, money, PortfolioSummary, RebalancePlan, type FactorPlan, type ValueHistory, type ValuePoint } from '../lib/api'
import { Portfolio, Position, Transaction } from '../types'
import { toast } from 'sonner'
import { ArrowLeft, Pencil, Trash2, Plus, X, Search, RefreshCw, Sparkles, Send, Zap, Activity, Link2, AlertTriangle } from 'lucide-react'
import BrokerCompareCard from '../components/BrokerCompareCard'
import { format } from 'date-fns'
import ValueChart, { periodStart, type Period } from '../components/ValueChart'
import { CompanyLink } from '../components/CompanyPanel'
import { useTheme } from '../lib/theme'

interface PortfolioData {
  portfolio: Portfolio
  positions: Position[]
  snapshots: Record<string, unknown>[]
  transactions: Transaction[]
}

interface StockSearchResult {
  symbol: string
  name: string
}

export default function PortfolioDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingPrices, setLoadingPrices] = useState(false)
  const [priceProgress, setPriceProgress] = useState({ done: 0, total: 0 })
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [showDeletePortfolioModal, setShowDeletePortfolioModal] = useState(false)
  const [deletingPortfolio, setDeletingPortfolio] = useState(false)

  const [showEditModal, setShowEditModal] = useState(false)
  const [editingPosition, setEditingPosition] = useState<Position | null>(null)
  const [editQuantity, setEditQuantity] = useState('')
  const [editAvgCost, setEditAvgCost] = useState('')
  const [saving, setSaving] = useState(false)

  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletingPosition, setDeletingPosition] = useState<Position | null>(null)

  const [aiMode, setAiMode] = useState<'off' | 'suggestions' | 'autonomous'>('off')
  const [strategy, setStrategy] = useState<'rules' | 'factor'>('rules')
  const [savingAiMode, setSavingAiMode] = useState(false)

  const [brokerConnected, setBrokerConnected] = useState(false)
  const [brokerEnv, setBrokerEnv] = useState<'paper' | 'live' | null>(null)
  const [accountSummary, setAccountSummary] = useState<{
    account_id?: string
    currency?: string
    cash?: number
    nav?: number
    buying_power?: number
    server_time?: string
  } | null>(null)
  const [syncingBroker, setSyncingBroker] = useState(false)

  const [showRebalanceDrawer, setShowRebalanceDrawer] = useState(false)
  const [rebalanceLoading, setRebalanceLoading] = useState(false)
  const [rebalancePlan, setRebalancePlan] = useState<RebalancePlan | null>(null)
  const [executingRebalance, setExecutingRebalance] = useState(false)
  const [rebalanceKey, setRebalanceKey] = useState('')
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [history, setHistory] = useState<ValueHistory | null>(null)
  const [historyFailed, setHistoryFailed] = useState(false)
  const [period, setPeriod] = useState<Period>('All')
  const [plan, setPlan] = useState<FactorPlan | null>(null)
  const [keepWithin, setKeepWithin] = useState(40)
  const [profiles, setProfiles] = useState<Record<string, { name: string; sector: string }>>({})
  const [pendingHere, setPendingHere] = useState(0)
  const [showAllHoldings, setShowAllHoldings] = useState(false)

  useEffect(() => {
    if (!id) return
    factorsApi.plan(Number(id)).then((r) => { setPlan(r.data.plan); setKeepWithin(r.data.keep_within) }).catch(() => undefined)
    aiApi.listSignals('pending').then((r) => setPendingHere((Array.isArray(r.data) ? r.data : [])
      .filter((sig: { portfolio_id?: number }) => sig.portfolio_id === Number(id)).length)).catch(() => undefined)
  }, [id, strategy])

  useEffect(() => {
    const symbols = data?.positions.map((p) => p.symbol) ?? []
    if (symbols.length) stocksApi.profiles(symbols).then((r) => setProfiles(r.data)).catch(() => undefined)
  }, [data])

  const [showAddModal, setShowAddModal] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [selectedStock, setSelectedStock] = useState<StockSearchResult | null>(null)
  const [addQuantity, setAddQuantity] = useState('')
  const [addAvgCost, setAddAvgCost] = useState('')

  useEffect(() => {
    if (id) {
      loadPortfolio()
      loadBrokerStatus()
    }
  }, [id])

  const loadBrokerStatus = async () => {
    try {
      const res = await brokerApi.getStatus()
      const s = res.data
      setBrokerConnected(!!s?.tws_configured)
      setBrokerEnv(s?.mode === 'tws_live' ? 'live' : s?.mode === 'tws_paper' ? 'paper' : null)
    } catch {
      setBrokerConnected(false)
    }
  }

  const handleSyncBroker = async () => {
    if (!brokerConnected) {
      toast.error('Set up the Interactive Brokers TWS connection first')
      navigate('/brokerage')
      return
    }
    // The TWS connector records every fill as it happens; this just reloads the latest figures.
    setSyncingBroker(true)
    setAccountSummary(null)
    await loadPortfolio()
    toast.success(data?.portfolio.trading_environment
      ? 'Refreshed. Holdings follow your IBKR fills automatically; compare them with your account below.'
      : 'Refreshed. This portfolio is not bought at IBKR yet; compare it with your account below.')
    setSyncingBroker(false)
  }

  const handleAiModeChange = async (mode: 'off' | 'suggestions' | 'autonomous') => {
    if (!id || mode === aiMode) return
    setSavingAiMode(true)
    const previous = aiMode
    setAiMode(mode)
    try {
      await aiApi.setPortfolioMode(Number(id), mode)
      toast.success(`AI mode set to ${mode}`)
    } catch (e: unknown) {
      setAiMode(previous)
      const err = e as { response?: { data?: { detail?: string } } }
      toast.error(apiErrorMessage(err, 'Failed to update AI mode'))
    } finally {
      setSavingAiMode(false)
    }
  }

  const [scanning, setScanning] = useState(false)
  const handleScanNow = async () => {
    if (!id) return
    setScanning(true)
    try {
      const res = await aiApi.scan(Number(id))
      const created = (res.data?.new_signals || []).length
      if (created) {
        toast.success(`${created} new proposal(s). Review them in the AI Inbox.`, {
          action: { label: 'Open', onClick: () => navigate('/ai-inbox') } })
      } else {
        const why = (res.data?.skipped || [])[0]?.reason
        toast.info(why ? `No new proposals (${why}).` : 'No new proposals: nothing meets your rules right now.')
      }
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, 'The check could not run'))
    } finally {
      setScanning(false)
    }
  }

  const openRebalanceDrawer = async () => {
    if (!id) return
    setShowRebalanceDrawer(true)
    setRebalanceLoading(true)
    setRebalancePlan(null)
    try {
      const res = await portfolioApi.getRebalancePlan(Number(id))
      setRebalancePlan(res.data as RebalancePlan)
      setRebalanceKey(crypto.randomUUID())  // the reviewed plan is sent once; retries reuse the key
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, 'Failed to compute rebalance plan'))
      setShowRebalanceDrawer(false)
    } finally {
      setRebalanceLoading(false)
    }
  }

  const handleExecuteRebalance = async () => {
    if (!id || !rebalancePlan?.legs.length || !rebalancePlan.can_execute) return
    setExecutingRebalance(true)
    try {
      const res = await portfolioApi.executeRebalance(Number(id), rebalancePlan.legs, rebalanceKey)
      const refused = res.data.results.filter((r) => !r.ok)
      if (res.data.queued) toast.success(res.data.message)
      for (const r of refused.slice(0, 3)) toast.error(`${r.side} ${r.symbol}: ${r.message}`)
      if (res.data.queued && !refused.length) setShowRebalanceDrawer(false)
      await loadPortfolio()
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e, 'The orders were refused'))
    } finally {
      setExecutingRebalance(false)
    }
  }

  const loadPortfolio = async () => {
    try {
      const response = await portfolioApi.detail(Number(id))
      setData(response.data)
      portfolioApi.history(Number(id)).then((r) => { setHistory(r.data); setHistoryFailed(false) })
        .catch(() => setHistoryFailed(true))
      setAiMode(response.data.portfolio?.ai_mode || 'off')
      setStrategy(response.data.portfolio?.strategy === 'factor' ? 'factor' : 'rules')

      const symbols = response.data.positions.map((p: Position) => p.symbol)
      if (symbols.length > 0) {
        loadCurrentPrices(symbols)
      }
    } catch {
      toast.error('Failed to load portfolio')
    } finally {
      setLoading(false)
    }
  }

  // One engine call values the whole portfolio (cash, realised profit, missing prices).
  const loadCurrentPrices = async (symbols: string[]) => {
    setLoadingPrices(true)
    setPriceProgress({ done: 0, total: symbols.length })
    try {
      const response = await portfolioApi.summary(Number(id))
      const prices: Record<string, number> = {}
      for (const h of response.data.holdings) prices[h.symbol] = h.price ?? 0
      setCurrentPrices(prices)
      setSummary(response.data)
    } catch {
      setSummary(null)
    }
    setPriceProgress({ done: symbols.length, total: symbols.length })
    setLoadingPrices(false)
  }

  const openEditModal = (position: Position) => {
    setEditingPosition(position)
    setEditQuantity(String(Number(position.quantity)))
    setEditAvgCost(String(Number(position.avg_cost)))
    setShowEditModal(true)
  }

  const handleUpdatePosition = async () => {
    if (!editingPosition || !id) return

    const quantity = parseFloat(editQuantity)
    const avgCost = parseFloat(editAvgCost)

    if (isNaN(quantity) || quantity < 0) {
      toast.error('Please enter a valid quantity')
      return
    }
    if (isNaN(avgCost) || avgCost <= 0) {
      toast.error('Please enter a valid average cost')
      return
    }

    setSaving(true)
    try {
      await portfolioApi.updatePosition(Number(id), editingPosition.id, quantity, avgCost)
      toast.success('Position updated successfully')
      setShowEditModal(false)
      loadPortfolio()
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(apiErrorMessage(err, 'Failed to update position'))
    } finally {
      setSaving(false)
    }
  }

  const openDeleteModal = (position: Position) => {
    setDeletingPosition(position)
    setShowDeleteModal(true)
  }

  const handleDeletePosition = async () => {
    if (!deletingPosition || !id) return

    setSaving(true)
    try {
      await portfolioApi.removePosition(Number(id), deletingPosition.id)
      toast.success('Position removed successfully')
      setShowDeleteModal(false)
      loadPortfolio()
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(apiErrorMessage(err, 'Failed to remove position'))
    } finally {
      setSaving(false)
    }
  }

  const handleDeletePortfolio = async () => {
    if (!id || !data) return
    setDeletingPortfolio(true)
    try {
      await portfolioApi.deletePortfolio(Number(id))
      toast.success(`"${data.portfolio.name}" deleted`)
      navigate('/portfolios')
    } catch {
      toast.error('Failed to delete portfolio')
      setDeletingPortfolio(false)
    }
  }

  const handleSearch = async (query: string) => {
    setSearchQuery(query)
    if (query.length < 2) {
      setSearchResults([])
      return
    }

    setSearching(true)
    try {
      const response = await stocksApi.search(query)
      setSearchResults(response.data.slice(0, 10))
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const selectStockToAdd = async (stock: StockSearchResult) => {
    setSelectedStock(stock)
    setSearchResults([])
    setSearchQuery(stock.symbol.replace('.AX', ''))
    
    try {
      const response = await stocksApi.info(stock.symbol)
      setAddAvgCost(String(response.data.current_price.toFixed(2)))
    } catch {
      setAddAvgCost('')
    }
  }

  const handleAddStock = async () => {
    if (!selectedStock || !id) return

    const quantity = parseFloat(addQuantity)
    const avgCost = parseFloat(addAvgCost)

    if (isNaN(quantity) || quantity <= 0) {
      toast.error('Please enter a valid quantity')
      return
    }
    if (isNaN(avgCost) || avgCost <= 0) {
      toast.error('Please enter a valid price')
      return
    }

    setSaving(true)
    try {
      await portfolioApi.addStock(Number(id), selectedStock.symbol, quantity, avgCost)
      toast.success(`${selectedStock.symbol.replace('.AX', '')} added to portfolio`)
      setShowAddModal(false)
      setSelectedStock(null)
      setSearchQuery('')
      setAddQuantity('')
      setAddAvgCost('')
      loadPortfolio()
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(apiErrorMessage(err, 'Failed to add stock'))
    } finally {
      setSaving(false)
    }
  }

  const modalStyle = {
    background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)',
    borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)',
    backdropFilter: 'blur(12px)',
    boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.5)' : '0 8px 32px rgba(0, 0, 0, 0.15)'
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-12">
        <p className={isDark ? 'text-slate-400' : 'text-slate-600'}>Portfolio not found</p>
        <Link to="/portfolios" className="text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 mt-2 inline-block">
          Back to portfolios
        </Link>
      </div>
    )
  }

  const { portfolio, positions, transactions } = data
  // Bought at IBKR: holdings follow real fills, so they can't be edited by hand.
  const atBroker = !!portfolio.trading_environment

  const totalValue = positions.reduce((sum, p) => {
    if (p.status !== 'active') return sum
    const price = currentPrices[p.symbol] || Number(p.avg_cost)
    return sum + (price * Number(p.quantity))
  }, 0)

  const costBasis = positions.reduce((sum, p) => {
    if (p.status !== 'active') return sum
    return sum + (Number(p.avg_cost) * Number(p.quantity))
  }, 0)

  // The engine's figures (with cash and realised profit) when available.
  const totalReturn = summary ? summary.total_return : totalValue - costBasis
  const totalReturnPct = summary ? summary.total_return_pct : costBasis > 0 ? ((totalValue - costBasis) / costBasis) * 100 : 0

  const currency: 'AUD' | 'USD' = summary?.currency ?? ((portfolio.market || 'ASX') === 'US' ? 'USD' : 'AUD')
  const accent = currency === 'USD' ? 'var(--usd)' : 'var(--aud)'
  const sym = currency === 'USD' ? 'US$' : 'A$'
  const valueNow = summary ? summary.total_value : totalValue
  const signedMoney = (v: number) => `${v >= 0 ? '+' : '-'}${money(Math.abs(v), currency, 0)}`
  const arrowPct = (v: number) => `${v >= 0 ? '▲ +' : '▼ -'}${Math.abs(v).toFixed(1)}%`
  const tone = (v: number) => (v >= 0 ? 'var(--pos)' : 'var(--neg)')
  const today = dayChange(history?.points ?? [])
  const vsMarket = (() => {
    const pts = history?.points ?? []
    const bench = history?.benchmark ?? []
    if (pts.length < 2 || bench.length < 2 || pts[0].value <= 0) return null
    const mine = (pts[pts.length - 1].value / pts[0].value - 1) * 100
    const market = (bench[bench.length - 1].value / bench[0].value - 1) * 100
    return mine - market
  })()
  const startedOn = history ? new Date(`${history.start}T00:00:00`) : new Date(portfolio.created_at)
  const startedLabel = startedOn.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  const holdingRows = positions
    .filter((p) => p.status === 'active')
    // 0 shares and nothing planned: a stock this portfolio no longer holds or wants (e.g. after a sale).
    .filter((p) => Number(p.quantity) > 0 || Number(p.planned_quantity ?? 0) > 0 || !atBroker)
    .map((p) => {
      const h = summary?.holdings.find((x) => x.symbol === p.symbol)
      const price = h?.price ?? currentPrices[p.symbol] ?? null
      const value = h ? h.value : (price ?? Number(p.avg_cost)) * Number(p.quantity)
      const cost = Number(p.avg_cost) * Number(p.quantity)
      return { position: p, price, value, gainPct: cost > 0 ? ((value - cost) / cost) * 100 : null,
        weight: valueNow > 0 ? (value / valueNow) * 100 : 0, profile: profiles[p.symbol] }
    })
    .sort((x, y) => y.value - x.value)
  const maxWeight = Math.max(1, ...holdingRows.map((r) => r.weight))
  const shownHoldings = showAllHoldings ? holdingRows : holdingRows.slice(0, 8)
  const heldCount = holdingRows.filter((r) => Number(r.position.quantity) > 0).length
  const sliceOf = (symbol: string) => (strategy === 'factor' && plan?.slices && symbol in plan.slices ? `Slice ${plan.slices[symbol] + 1}` : '')
  const sectors = (() => {
    const totals: Record<string, number> = {}
    for (const r of holdingRows) {
      if (r.value <= 0) continue
      const name = r.profile?.sector ?? 'Other'
      totals[name] = (totals[name] ?? 0) + r.value
    }
    const cash = summary?.cash ?? 0
    const rows = Object.entries(totals).sort((a, b) => b[1] - a[1]).map(([name, v]) => ({ name, value: v }))
    if (cash > 0 && valueNow > 0 && cash / valueNow >= 0.005) rows.push({ name: 'Cash', value: cash })
    const total = rows.reduce((a, r) => a + r.value, 0)
    return rows.map((r) => ({ ...r, pct: total > 0 ? (r.value / total) * 100 : 0 }))
  })()
  const maxSector = Math.max(1, ...sectors.map((x) => x.pct))
  const envLabel = portfolio.trading_environment === 'live' ? 'TWS live' : portfolio.trading_environment === 'paper' ? 'TWS paper' : 'Research only'
  const modeLabel = aiMode === 'autonomous' ? 'Fully automatic' : aiMode === 'suggestions' ? 'Asks first' : 'AI Trading off'
  const kpis: { label: string; value: string; sub: string; color?: string; subColor?: string }[] = [
    { label: 'Value', value: money(valueNow, currency, 0),
      sub: summary ? `Holdings ${money(summary.market_value, currency, 0)} + cash ${money(summary.cash, currency, 0)}` : 'Shares at the latest price' },
    { label: 'Total return', value: signedMoney(totalReturn), color: tone(totalReturn), subColor: tone(totalReturn),
      sub: `${arrowPct(totalReturnPct)} since ${startedLabel}` },
    today
      ? { label: 'Today', value: signedMoney(today.amount), color: tone(today.amount), subColor: tone(today.amount), sub: arrowPct(today.pct) }
      : { label: 'Today', value: '—', sub: 'Needs two days of prices' },
    vsMarket === null
      ? { label: `vs ${history?.benchmark_name ?? (currency === 'USD' ? 'S&P 500' : 'ASX 200')}`, value: '—', sub: 'Not enough history yet' }
      : { label: `vs ${history?.benchmark_name}`, value: `${vsMarket >= 0 ? '+' : ''}${vsMarket.toFixed(1)}%`, color: tone(vsMarket),
          sub: `${vsMarket >= 0 ? 'Ahead' : 'Behind'} since it was bought` },
    { label: 'Fees paid', value: money(summary?.fees ?? 0, currency, 0),
      sub: `${transactions.length} trade${transactions.length === 1 ? '' : 's'}${summary && valueNow > 0 ? ` · ${((summary.fees / valueNow) * 100).toFixed(1)}% of value` : ''}` },
  ]

  return (
    <div className="max-w-7xl mx-auto space-y-5 animate-fade-in">
      <header className="space-y-3">
        <nav aria-label="Breadcrumb" className="text-sm theme-text-muted flex items-center gap-1.5">
          <Link to="/portfolios" className="hover:underline flex items-center gap-1"><ArrowLeft className="w-3.5 h-3.5" /> Portfolios</Link>
          <span>/</span><span className="theme-text-secondary truncate">{portfolio.name}</span>
        </nav>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2 min-w-0">
            <h1 className="page-title">{portfolio.name}</h1>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`chip ${currency === 'USD' ? 'chip-usd' : 'chip-aud'}`}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: accent }} />{currency === 'USD' ? 'US · US$' : 'ASX · A$'}
              </span>
              <span className="chip">{strategy === 'factor' ? 'Model B' : 'Simple rules'} · {heldCount} stock{heldCount === 1 ? '' : 's'}</span>
              <span className="chip" style={portfolio.trading_environment === 'live' ? { background: 'var(--neg-tint)', color: 'var(--neg)' } : undefined}>{envLabel}</span>
              <span className="chip" style={aiMode === 'autonomous' ? { background: 'var(--pos-tint)', color: 'var(--pos)' } : undefined}>{modeLabel}</span>
              <span className="chip capitalize">{portfolio.risk_tolerance}</span>
              <span className="text-xs theme-text-muted ml-1">Created {format(new Date(portfolio.created_at), 'd MMM yyyy')}</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/paper-orders" className="btn-secondary text-sm !py-2 !px-4">Orders</Link>
            <Link to="/ai-trading" className="btn-secondary text-sm !py-2 !px-4">Settings</Link>
            {pendingHere > 0 && (
              <Link to="/ai-inbox" className="btn-primary text-sm !py-2 !px-4">Review {pendingHere} proposal{pendingHere === 1 ? '' : 's'}</Link>
            )}
            <button onClick={handleSyncBroker} disabled={syncingBroker} className="btn-secondary text-sm !py-2 !px-3 flex items-center gap-1.5"
              title={brokerConnected ? `Reload from IBKR (${brokerEnv})` : 'Connect IBKR first'}>
              {syncingBroker ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Refresh
            </button>
            <button onClick={openRebalanceDrawer} className="btn-secondary text-sm !py-2 !px-3 flex items-center gap-1.5">
              <Send className="w-4 h-4" /> Rebalance
            </button>
            <button onClick={() => setShowAddModal(true)} disabled={atBroker} className="btn-secondary text-sm !py-2 !px-3 flex items-center gap-1.5"
              title={atBroker ? 'This portfolio follows your IBKR fills; buy more with an order instead' : undefined}>
              <Plus className="w-4 h-4" /> Add stock
            </button>
            <button onClick={() => setShowDeletePortfolioModal(true)} className="btn-secondary text-sm !py-2 !px-3 flex items-center gap-1.5 text-neg"
              title="Delete this portfolio">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {loadingPrices && (
        <div className="flex items-center gap-2 text-sm theme-text-secondary">
          <RefreshCw className="w-4 h-4 animate-spin" /> Fetching prices… {priceProgress.total > 0 ? `${priceProgress.done} / ${priceProgress.total}` : ''}
        </div>
      )}
      {summary && summary.prices_missing.length > 0 && (
        <p className="text-sm flex items-center gap-2" style={{ color: 'var(--aud)' }} data-testid="prices-missing">
          <AlertTriangle className="w-4 h-4" /> No current price for {summary.prices_missing.join(', ')} (Yahoo didn't answer).
          Those holdings are valued at what they cost until a price comes back.
        </p>
      )}

      <section aria-label="Key numbers" className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="portfolio-money">
        {kpis.map((k) => (
          <div key={k.label} className="stat-card !p-4 space-y-1">
            <p className="text-xs theme-text-muted">{k.label}</p>
            {loadingPrices && !summary ? <div className="h-7 w-24 rounded-lg loading-shimmer" /> : (
              <p className="num text-xl font-semibold" style={{ color: k.color ?? 'var(--text-primary)' }}>{k.value}</p>
            )}
            <p className="num text-[11px]" style={{ color: k.subColor ?? 'var(--text-muted)' }}>{k.sub}</p>
          </div>
        ))}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2">
          <GrowthCard history={history} failed={historyFailed} period={period} onPeriod={setPeriod}
            valueNow={summary?.total_value ?? null} expectedReturn={Number(portfolio.expected_return || 0)} />
        </div>
        <PlanCard strategy={strategy} plan={plan} keepWithin={keepWithin} />
      </div>

      <section aria-label="Holdings" className="card !p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <h2 className="text-base font-semibold theme-text">Holdings</h2>
          <span className="text-xs theme-text-muted">
            {holdingRows.length} stock{holdingRows.length === 1 ? '' : 's'}{!showAllHoldings && holdingRows.length > 8 ? ' · showing the 8 largest' : ''}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider theme-text-muted border-b theme-border">
                <th className="px-5 py-2 font-semibold">Stock</th>
                <th className="py-2 font-semibold text-right">Shares</th>
                <th className="py-2 font-semibold text-right">Price</th>
                <th className="py-2 font-semibold text-right">Value</th>
                <th className="py-2 pl-6 font-semibold">Weight</th>
                <th className="py-2 font-semibold text-right">Gain</th>
                {strategy === 'factor' && <th className="py-2 pl-4 font-semibold">Slice</th>}
                <th className="py-2 pr-5 font-semibold text-right"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {shownHoldings.map(({ position, price, value, gainPct, weight, profile }) => {
                const code = position.symbol.replace('.AX', '')
                const planned = atBroker && position.planned_quantity != null && Number(position.quantity) < Number(position.planned_quantity)
                return (
                  <tr key={position.id} className="border-b theme-border last:border-b-0">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <span className="num text-[10px] font-semibold w-10 h-8 rounded-lg flex items-center justify-center shrink-0 surface-2 theme-text">
                          {code.slice(0, 4)}
                        </span>
                        <span className="min-w-0">
                          <CompanyLink symbol={position.symbol} className="block text-sm theme-text truncate max-w-[220px]">
                            {profile?.name ?? code}
                          </CompanyLink>
                          <span className="block text-xs theme-text-muted">{profile?.sector ?? code}</span>
                        </span>
                      </div>
                    </td>
                    <td className="py-3 text-right num theme-text">
                      {atBroker ? Number(position.quantity).toFixed(0) : Number(position.quantity).toFixed(2)}
                      {planned && (
                        <span className="block text-[11px]" style={{ color: 'var(--aud)' }}>of {Number(position.planned_quantity)} planned
                          {position.entry_state === 'waiting' ? ' · waiting for RSI dip' : position.entry_state === 'skipped' ? ' · skipped' : ''}</span>
                      )}
                    </td>
                    <td className="py-3 text-right num theme-text-secondary">
                      {price ? `${sym}${price.toFixed(2)}` : loadingPrices ? '…' : <span title="No current price from Yahoo">n/a</span>}
                    </td>
                    <td className="py-3 text-right num font-semibold theme-text">{money(value, currency, 0)}</td>
                    <td className="py-3 pl-6">
                      <span className="flex items-center gap-2">
                        <span className="h-1.5 w-24 rounded-full overflow-hidden" style={{ background: 'var(--chip)' }}>
                          <span className="block h-full rounded-full" style={{ width: `${(weight / maxWeight) * 100}%`, background: accent }} />
                        </span>
                        <span className="num text-xs theme-text-secondary w-12 text-right">{weight.toFixed(1)}%</span>
                      </span>
                    </td>
                    <td className="py-3 text-right num" style={{ color: gainPct === null ? 'var(--text-muted)' : tone(gainPct) }}>
                      {gainPct === null ? '—' : arrowPct(gainPct)}
                    </td>
                    {strategy === 'factor' && <td className="py-3 pl-4 text-xs theme-text-secondary">{sliceOf(position.symbol)}</td>}
                    <td className="py-3 pr-5 text-right">
                      {!atBroker && (
                        <span className="inline-flex gap-1">
                          <button onClick={() => openEditModal(position)} className="p-1.5 rounded theme-text-muted nav-hover" title="Edit position">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => openDeleteModal(position)} className="p-1.5 rounded theme-text-muted nav-hover" title="Remove position">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {holdingRows.length > 8 && (
          <div className="px-5 py-3 border-t theme-border">
            <button type="button" className="text-sm font-medium theme-text-secondary hover:underline" onClick={() => setShowAllHoldings(!showAllHoldings)}>
              {showAllHoldings ? 'Show the 8 largest' : `Show all ${holdingRows.length}`}
            </button>
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section aria-label="Sectors" className="card space-y-3">
          <h2 className="text-base font-semibold theme-text">Where the money is</h2>
          {sectors.length === 0 ? <p className="text-sm theme-text-muted">Nothing held yet.</p> : sectors.map((x) => (
            <div key={x.name} className="grid grid-cols-[minmax(0,9rem)_1fr_3rem] items-center gap-3 text-sm">
              <span className="theme-text-secondary truncate">{x.name}</span>
              <span className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--chip)' }}>
                <span className="block h-full rounded-full" style={{ width: `${(x.pct / maxSector) * 100}%`, background: x.name === 'Cash' ? 'var(--text-muted)' : accent }} />
              </span>
              <span className="num text-xs text-right theme-text">{x.pct.toFixed(0)}%</span>
            </div>
          ))}
        </section>

        <section aria-label="Recent activity" className="card space-y-2">
          <h2 className="text-base font-semibold theme-text">Recent activity</h2>
          {transactions.length === 0 ? <p className="text-sm theme-text-muted py-2">No trades yet.</p> : transactions.slice(0, 6).map((txn) => {
            const buy = txn.txn_type === 'buy'
            const qty = Number(txn.quantity)
            return (
              <div key={txn.id} className="flex items-center gap-3 py-2 border-b theme-border last:border-b-0">
                <span className="num text-[10px] font-semibold px-2 py-1 rounded-md shrink-0"
                  style={{ background: buy ? 'var(--pos-tint)' : 'var(--neg-tint)', color: buy ? 'var(--pos)' : 'var(--neg)' }}>
                  {txn.txn_type.toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm theme-text truncate">
                    {buy ? 'Bought' : 'Sold'} {Number.isInteger(qty) ? qty : qty.toFixed(2)} {txn.symbol.replace('.AX', '')} at {sym}{Number(txn.price).toFixed(2)}
                  </p>
                  <p className="text-xs theme-text-muted truncate">
                    {format(new Date(txn.txn_time), 'd MMM, h:mm a')}
                    {atBroker ? ` · filled at IBKR (${portfolio.trading_environment})` : ' · recorded in Sapient'}
                    {txn.notes ? ` · ${txn.notes}` : ''}
                  </p>
                </div>
                <span className="num text-sm theme-text">{money(Number(txn.total_amount), currency, 0)}</span>
              </div>
            )
          })}
        </section>
      </div>

      {/* AI Trading Mode + Broker Status row */}
      <div className="card flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`p-2.5 rounded-xl ${isDark ? 'bg-purple-500/15 text-purple-300' : 'bg-purple-100 text-purple-600'}`}>
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className={`text-sm font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>AI Trading Mode</h3>
            </div>
            <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {aiMode === 'off' && 'AI engine ignores this portfolio.'}
              {aiMode === 'suggestions' && 'AI sends signals to your inbox; you approve every trade.'}
              {aiMode === 'autonomous' && 'Fully automatic: once the portfolio is bought on paper or for real (below), Sapient trades it within your limits without asking.'}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
        <button onClick={handleScanNow} disabled={scanning || aiMode === 'off'} data-testid="scan-now"
          title={aiMode === 'off' ? 'Turn AI Trading on for this portfolio first' : 'Check this portfolio against your rules now'}
          className="btn-secondary text-sm flex items-center gap-1.5 disabled:opacity-50">
          {scanning ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />} Check now
        </button>
        <div className={`inline-flex p-1 rounded-xl border ${isDark ? 'bg-slate-900/50 border-slate-700/50' : 'bg-slate-100 border-slate-200'}`}>
          {(['off', 'suggestions', 'autonomous'] as const).map((m) => {
            const active = aiMode === m
            return (
              <button
                key={m}
                onClick={() => handleAiModeChange(m)}
                disabled={savingAiMode}
                className={`px-3 sm:px-4 py-1.5 text-xs sm:text-sm font-medium rounded-lg transition-all capitalize ${
                  active
                    ? m === 'autonomous'
                      ? 'bg-gradient-to-r from-purple-500 to-indigo-500 text-white shadow-lg shadow-purple-500/30'
                      : m === 'suggestions'
                      ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg shadow-sky-500/30'
                      : isDark ? 'bg-slate-700 text-slate-100' : 'bg-white text-slate-900 shadow-sm'
                    : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                } disabled:opacity-50`}
              >
                {m}
              </button>
            )
          })}
        </div>
        </div>
      </div>

      <FactorStrategy portfolioId={Number(id)} strategy={strategy} onStrategy={setStrategy} />

      {accountSummary && brokerConnected && (
        <div className={`card border ${isDark ? 'border-sky-500/30' : 'border-sky-200'}`}>
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <Activity className={`w-4 h-4 ${isDark ? 'text-sky-300' : 'text-sky-600'}`} />
              <h3 className={`text-sm font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                IBKR Account · {accountSummary.account_id}
              </h3>
              <span className={`text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-md ${isDark ? 'bg-slate-700/50 text-slate-300' : 'bg-slate-100 text-slate-600'}`}>
                {brokerEnv}
              </span>
            </div>
            <span className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
              {accountSummary.server_time && format(new Date(accountSummary.server_time), 'HH:mm:ss')}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div>
              <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Cash</p>
              <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {accountSummary.currency || ''} {(accountSummary.cash || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
            <div>
              <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Buying Power</p>
              <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {accountSummary.currency || ''} {(accountSummary.buying_power || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
            <div>
              <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Net Liq Value</p>
              <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {accountSummary.currency || ''} {(accountSummary.nav || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
          </div>
        </div>
      )}

      {id && <BrokerCompareCard portfolioId={Number(id)} />}

      {showEditModal && editingPosition && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ backgroundColor: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-xl p-6 w-full max-w-md mx-4 border" style={modalStyle}>
            <div className="flex items-center justify-between mb-4">
              <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                Edit {editingPosition.symbol.replace('.AX', '')}
              </h3>
              <button onClick={() => setShowEditModal(false)} className={`${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'} transition-colors`}>
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="label">Quantity (shares)</label>
                <input
                  type="number"
                  value={editQuantity}
                  onChange={(e) => setEditQuantity(e.target.value)}
                  className="input"
                  min="0"
                  step="0.01"
                />
                <p className="text-xs text-slate-500 mt-1">Set to 0 to close the position</p>
              </div>
              <div>
                <label className="label">Average Cost ($)</label>
                <input
                  type="number"
                  value={editAvgCost}
                  onChange={(e) => setEditAvgCost(e.target.value)}
                  className="input"
                  min="0"
                  step="0.01"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setShowEditModal(false)}
                  className="btn-secondary flex-1"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpdatePosition}
                  disabled={saving}
                  className="btn-primary flex-1"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showDeleteModal && deletingPosition && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ backgroundColor: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-xl p-6 w-full max-w-md mx-4 border" style={modalStyle}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-red-400">Remove Position</h3>
              <button onClick={() => setShowDeleteModal(false)} className={`${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'} transition-colors`}>
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <p className={isDark ? 'text-slate-400' : 'text-slate-600'} style={{ marginBottom: '1.5rem' }}>
              Are you sure you want to remove <span className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{deletingPosition.symbol.replace('.AX', '')}</span> from this portfolio? This action cannot be undone.
            </p>
            
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="btn-secondary flex-1"
              >
                Cancel
              </button>
              <button
                onClick={handleDeletePosition}
                disabled={saving}
                className="btn-danger flex-1"
              >
                {saving ? 'Removing...' : 'Remove'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddModal && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ backgroundColor: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-xl p-6 w-full max-w-md mx-4 border" style={modalStyle}>
            <div className="flex items-center justify-between mb-4">
              <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Add Stock to Portfolio</h3>
              <button 
                onClick={() => {
                  setShowAddModal(false)
                  setSelectedStock(null)
                  setSearchQuery('')
                  setAddQuantity('')
                  setAddAvgCost('')
                }} 
                className={`${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'} transition-colors`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              <div className="relative">
                <label className="label">Search Stock</label>
                <div className="relative">
                  <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    placeholder="Search ASX stocks..."
                    className="input pl-10"
                  />
                </div>
                {searchResults.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full rounded-lg shadow-lg max-h-48 overflow-y-auto border" style={{ background: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.95)', borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)', backdropFilter: 'blur(12px)' }}>
                    {searchResults.map((stock) => (
                      <button
                        key={stock.symbol}
                        onClick={() => selectStockToAdd(stock)}
                        className={`w-full text-left px-4 py-2 ${isDark ? 'hover:bg-slate-700/50' : 'hover:bg-slate-100'} flex justify-between ${isDark ? 'text-slate-100' : 'text-slate-900'} transition-colors`}
                      >
                        <span className="font-medium">{stock.symbol.replace('.AX', '')}</span>
                        <span className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'} truncate ml-2`}>{stock.name}</span>
                      </button>
                    ))}
                  </div>
                )}
                {searching && (
                  <p className="text-sm text-slate-500 mt-1">Searching...</p>
                )}
              </div>

              {selectedStock && (
                <>
                  <div className={`p-3 rounded-lg border ${isDark ? 'bg-sky-500/20 border-sky-500/30' : 'bg-sky-50 border-sky-200'}`}>
                    <p className="font-medium text-sky-700 dark:text-sky-300">{selectedStock.symbol.replace('.AX', '')}</p>
                    <p className="text-sm text-sky-600 dark:text-sky-400">{selectedStock.name}</p>
                  </div>
                  
                  <div>
                    <label className="label">Quantity (shares)</label>
                    <input
                      type="number"
                      value={addQuantity}
                      onChange={(e) => setAddQuantity(e.target.value)}
                      className="input"
                      min="0"
                      step="0.01"
                      placeholder="e.g., 100"
                    />
                  </div>
                  <div>
                    <label className="label">Purchase Price ($)</label>
                    <input
                      type="number"
                      value={addAvgCost}
                      onChange={(e) => setAddAvgCost(e.target.value)}
                      className="input"
                      min="0"
                      step="0.01"
                      placeholder="e.g., 25.50"
                    />
                    <p className="text-xs text-slate-500 mt-1">Pre-filled with current market price</p>
                  </div>
                </>
              )}
              
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => {
                    setShowAddModal(false)
                    setSelectedStock(null)
                    setSearchQuery('')
                    setAddQuantity('')
                    setAddAvgCost('')
                  }}
                  className="btn-secondary flex-1"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddStock}
                  disabled={saving || !selectedStock}
                  className="btn-primary flex-1"
                >
                  {saving ? 'Adding...' : 'Add Stock'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showDeletePortfolioModal && data && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className={`rounded-2xl border max-w-md w-full p-6 shadow-2xl`} style={modalStyle}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-500/20 rounded-xl border border-red-500/30">
                  <Trash2 className="w-5 h-5 text-red-400" />
                </div>
                <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Delete Portfolio</h2>
              </div>
              <button onClick={() => setShowDeletePortfolioModal(false)} className="text-slate-400 hover:text-slate-300">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className={`text-sm mb-2 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Are you sure you want to delete <span className="font-semibold text-red-400">"{data.portfolio.name}"</span>?
            </p>
            <p className={`text-sm mb-6 ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
              This will permanently remove all positions, transactions and history. This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeletePortfolioModal(false)}
                className="btn-secondary flex-1"
                disabled={deletingPortfolio}
              >
                Cancel
              </button>
              <button
                onClick={handleDeletePortfolio}
                disabled={deletingPortfolio}
                className="flex-1 px-4 py-2.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-xl border border-red-500/30 font-medium transition-all duration-200 disabled:opacity-50"
              >
                {deletingPortfolio ? 'Deleting...' : 'Delete Portfolio'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Pending Broker Sync drawer */}
      {showRebalanceDrawer && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in" onClick={() => !executingRebalance && setShowRebalanceDrawer(false)}>
          <div
            className={`max-w-2xl w-full rounded-2xl border ${isDark ? 'border-slate-700/50' : 'border-slate-200'} max-h-[90vh] flex flex-col`}
            style={modalStyle}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`flex items-center justify-between px-6 py-4 border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-600'}`}>
                  <Send className="w-5 h-5" />
                </div>
                <div>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Rebalance to target weights</h2>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    {rebalancePlan?.environment === 'live' ? 'REAL-MONEY orders in your live account'
                      : rebalancePlan?.environment === 'paper' ? 'Paper orders in your TWS paper account'
                      : 'Information only (this portfolio is not at Interactive Brokers)'} · limit DAY · whole shares
                  </p>
                </div>
              </div>
              <button onClick={() => !executingRebalance && setShowRebalanceDrawer(false)} className={`${isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-500 hover:text-slate-800'}`}>
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              {rebalanceLoading && (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className={`w-6 h-6 animate-spin ${isDark ? 'text-sky-400' : 'text-sky-600'}`} />
                </div>
              )}

              {!rebalanceLoading && rebalancePlan && rebalancePlan.legs.length === 0 && (
                <div className="text-center py-12">
                  <div className={`inline-flex p-3 rounded-full mb-3 ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-600'}`}>
                    <Zap className="w-6 h-6" />
                  </div>
                  <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                    Nothing to rebalance
                  </p>
                  <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{rebalancePlan.notes}</p>
                </div>
              )}

              {!rebalanceLoading && rebalancePlan && rebalancePlan.legs.length > 0 && (
                <>
                  <div className={`grid grid-cols-3 gap-3 mb-4 text-sm`}>
                    <div className={`p-3 rounded-xl ${isDark ? 'bg-slate-800/50' : 'bg-slate-50'}`}>
                      <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Value incl. cash</p>
                      <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                        ${rebalancePlan.portfolio_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </div>
                    <div className={`p-3 rounded-xl ${isDark ? 'bg-slate-800/50' : 'bg-slate-50'}`}>
                      <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Cash</p>
                      <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                        ${rebalancePlan.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </div>
                    <div className={`p-3 rounded-xl ${isDark ? 'bg-slate-800/50' : 'bg-slate-50'}`}>
                      <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Estimated turnover</p>
                      <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                        ${rebalancePlan.total_drift_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {rebalancePlan.legs.map((leg, idx) => (
                      <div
                        key={`${leg.symbol}-${idx}`}
                        className={`p-3 rounded-xl border flex items-center justify-between ${
                          isDark ? 'border-slate-700/50 bg-slate-800/30' : 'border-slate-200 bg-white'
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span
                            className={`px-2 py-1 rounded-md text-xs font-bold ${
                              leg.side === 'BUY'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-red-500/20 text-red-400 border border-red-500/30'
                            }`}
                          >
                            {leg.side}
                          </span>
                          <div className="min-w-0">
                            <p className={`font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                              {leg.symbol.replace('.AX', '')}
                              <span className={`ml-2 text-xs font-normal ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                                {leg.quantity} shares · about ${leg.price.toFixed(2)} each
                              </span>
                            </p>
                            <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
                              Drift {leg.drift_pct.toFixed(1)}pp · target {(leg.target_weight * 100).toFixed(1)}% · current {(leg.current_weight * 100).toFixed(1)}%
                            </p>
                          </div>
                        </div>
                        <p className={`text-sm font-semibold tabular-nums shrink-0 ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                          ${leg.estimated_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </p>
                      </div>
                    ))}
                  </div>

                  <p className="text-xs theme-text-muted mt-4">{rebalancePlan.notes} Each order still goes through your
                    limits and TWS's own price check; the limit price is set from TWS's price when it is sent.</p>
                </>
              )}
            </div>

            <div className={`flex gap-3 px-6 py-4 border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
              <button
                onClick={() => setShowRebalanceDrawer(false)}
                disabled={executingRebalance}
                className="btn-secondary flex-1"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteRebalance}
                disabled={executingRebalance || !rebalancePlan?.can_execute}
                className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {executingRebalance ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Placing…
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    {rebalancePlan?.can_execute
                      ? `Place ${rebalancePlan.legs.length} ${rebalancePlan.environment === 'live' ? 'REAL-MONEY' : 'paper'} order(s)`
                      : rebalancePlan?.environment ? 'Trading is switched off for this account' : 'Buy this portfolio at IBKR to rebalance'}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Change since the previous trading day's close (null without two days of values). */
function dayChange(points: ValuePoint[]) {
  if (points.length < 2) return null
  const now = points[points.length - 1].value
  const before = points[points.length - 2].value
  return { amount: now - before, pct: before > 0 ? ((now - before) / before) * 100 : 0 }
}

const PORTFOLIO_PERIODS: Period[] = ['1W', '1M', '3M', 'All']

/** Value since the start against the market index and the original forecast, so you can see how closely it is tracking. */
function GrowthCard({ history, failed, period, onPeriod, valueNow, expectedReturn }: {
  history: ValueHistory | null; failed: boolean; period: Period; onPeriod: (p: Period) => void
  valueNow: number | null; expectedReturn: number
}) {
  const currency = history?.currency ?? 'AUD'
  const color = currency === 'USD' ? 'var(--usd)' : 'var(--aud)'
  const benchName = history?.benchmark_name ?? (currency === 'USD' ? 'S&P 500' : 'ASX 200')
  const tracking = (() => {
    if (!history || history.money_put_in <= 0) return null
    const lastDay = history.points[history.points.length - 1]?.date ?? history.start
    const years = (new Date(`${lastDay}T00:00:00`).getTime() - new Date(`${history.start}T00:00:00`).getTime()) / (365 * 86400000)
    const forecastNow = history.money_put_in * (1 + history.expected_return) ** Math.max(years, 0)
    const actual = valueNow ?? history.points[history.points.length - 1]?.value
    if (actual == null) return null
    return { forecastNow, actual, gap: actual - forecastNow }
  })()
  // Growth over the chosen period, for the legend chips.
  const change = (points: ValuePoint[]) => {
    const from = periodStart(period)
    const inside = points.filter((p) => p.date >= from)
    if (inside.length < 2 || inside[0].value <= 0) return null
    return (inside[inside.length - 1].value / inside[0].value - 1) * 100
  }
  const mine = history ? change(history.points) : null
  const market = history ? change(history.benchmark ?? []) : null
  const chip = (v: number | null) => v === null ? '—' : `${v >= 0 ? '▲ +' : '▼ -'}${Math.abs(v).toFixed(1)}%`
  const series = history ? [
    { key: 'value', label: 'This portfolio', color, points: history.points },
    { key: 'bench', label: benchName, color: 'var(--text-muted)', points: history.benchmark ?? [], dashed: true },
    { key: 'forecast', label: 'Original forecast', color: 'var(--usd)', points: history.forecast, dashed: true },
  ] : []
  // The forecast line stops at today, so the real history keeps the whole width.
  const until = history?.points.length ? history.points[history.points.length - 1].date : undefined
  return (
    <section aria-label="Growth" className="card space-y-4 h-full" data-testid="growth-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold theme-text">Growth vs the {benchName} and the forecast</h2>
          <p className="text-xs theme-text-muted">Value of shares + cash since the portfolio was bought</p>
        </div>
        <div className="seg" role="group" aria-label="Period">
          {PORTFOLIO_PERIODS.map((p) => (
            <button key={p} type="button" aria-pressed={period === p} onClick={() => onPeriod(p)}>{p}</button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs theme-text-secondary">
        <span className="flex items-center gap-2"><span className="w-4 h-0.5 rounded" style={{ background: color }} />
          This portfolio <strong className="num" style={{ color: mine === null ? undefined : mine >= 0 ? 'var(--pos)' : 'var(--neg)' }}>{chip(mine)}</strong></span>
        <span className="flex items-center gap-2"><span className="w-4 border-t-2 border-dashed" style={{ borderColor: 'var(--text-muted)' }} />
          {benchName} <strong className="num" style={{ color: market === null ? undefined : market >= 0 ? 'var(--pos)' : 'var(--neg)' }}>{chip(market)}</strong></span>
        <span className="flex items-center gap-2"><span className="w-4 border-t-2 border-dashed" style={{ borderColor: 'var(--usd)' }} />
          Original forecast <span className="num">({(expectedReturn * 100).toFixed(1)}% a year)</span></span>
      </div>
      {tracking && (
        <p className="text-sm theme-text-secondary">
          Now <span className="num font-semibold theme-text">{money(tracking.actual, currency, 0)}</span>
          {' · '}forecast for today <span className="num">{money(tracking.forecastNow, currency, 0)}</span>
          {' · '}
          <span className="num font-semibold" style={{ color: tracking.gap >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
            {tracking.gap >= 0 ? '▲ ' : '▼ '}{money(Math.abs(tracking.gap), currency, 0)} {tracking.gap >= 0 ? 'ahead of' : 'behind'} the forecast
          </span>
        </p>
      )}
      {failed ? <p className="text-sm theme-text-muted py-10 text-center">Couldn't rebuild the history right now (Yahoo didn't answer).</p>
        : !history ? <div className="h-[260px] rounded-xl loading-shimmer" />
        : <ValueChart series={series} period={period} prefix={currency === 'USD' ? 'US$' : 'A$'} height={260}
            until={until} />}
      <p className="text-[11px] theme-text-muted">
        The {benchName} line shows what the same money would have done in the index. The forecast is the yearly return the
        optimiser expected when you built this portfolio, from the past two years of prices: usually optimistic, a yardstick
        rather than a promise.{history?.missing_prices.length ? ` No price history for ${history.missing_prices.join(', ')}.` : ''}
      </p>
    </section>
  )
}

const monthName = (ym: string, add: number) => {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y, m - 1 + add, 1).toLocaleDateString(undefined, { month: 'short' })
}

/** Model B: the three slices, which was reviewed last and which is next. Simple rules: what the rules do. */
function PlanCard({ strategy, plan, keepWithin }: { strategy: 'rules' | 'factor'; plan: FactorPlan | null; keepWithin: number }) {
  if (strategy !== 'factor') {
    return (
      <section aria-label="How it's managed" className="card space-y-3">
        <h2 className="text-base font-semibold theme-text">Simple rules</h2>
        <p className="text-xs theme-text-muted">How AI Trading looks after this portfolio at its two checks each trading day.</p>
        {[
          'Buys a little when RSI(14) says a stock is oversold (with MACD agreeing).',
          'Sells some when RSI says it is overbought.',
          'Stop-loss and take-profit come from AI Settings.',
        ].map((t, i) => (
          <div key={t} className="flex gap-3 rounded-xl p-3 surface-2 text-sm theme-text-secondary">
            <span className="num w-6 h-6 shrink-0 rounded-md flex items-center justify-center text-xs font-semibold" style={{ background: 'var(--chip)' }}>{i + 1}</span>
            {t}
          </div>
        ))}
        <Link to="/ai-trading" className="text-sm font-medium theme-text-secondary hover:underline">Change the rules in AI Settings</Link>
      </section>
    )
  }
  const slices = plan?.slices ?? {}
  const reviewed = plan && !plan.adopted ? plan.slice ?? 0 : null
  const next = reviewed === null ? 0 : (reviewed + 1) % 3
  const stocksIn = (k: number) => {
    const list = Object.entries(slices).filter(([, v]) => v === k).map(([sym]) => sym.replace('.AX', ''))
    return list.length ? `${list.slice(0, 4).join(', ')}${list.length > 4 ? ` + ${list.length - 4}` : ''}` : 'No stocks yet'
  }
  return (
    <section aria-label="Model B plan" className="card space-y-3" data-testid="model-b-plan">
      <div>
        <h2 className="text-base font-semibold theme-text">Model B plan</h2>
        <p className="text-xs theme-text-muted">A third of the portfolio is re-checked each month, so every stock is reviewed once a quarter.</p>
      </div>
      {!plan ? <p className="text-sm theme-text-muted">The plan is made at the next scheduled check (AI Trading must be on).</p> : [0, 1, 2].map((k) => {
        const done = k === reviewed
        const isNext = k === next
        const monthsAhead = (k - next + 3) % 3 + 1
        const title = done ? `Slice ${k + 1} · reviewed ${monthName(plan.month, 0)}` : `Slice ${k + 1} · due early ${monthName(plan.month, monthsAhead)}`
        return (
          <div key={k} className="flex items-center gap-3 rounded-xl p-3 border"
            style={{ background: isNext ? 'var(--aud-tint)' : 'var(--surface-2)', borderColor: isNext ? 'var(--aud)' : 'var(--border-color)' }}>
            <span className="num w-7 h-7 shrink-0 rounded-lg flex items-center justify-center text-xs font-semibold"
              style={done ? { background: 'var(--pos-tint)', color: 'var(--pos)' } : isNext ? { background: 'var(--aud)', color: 'var(--on-ink)' } : { background: 'var(--chip)', color: 'var(--text-muted)' }}>
              {k + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold theme-text">{title}</p>
              <p className="text-xs theme-text-muted truncate">{stocksIn(k)}</p>
            </div>
            <span className="text-xs font-semibold" style={{ color: done ? 'var(--pos)' : isNext ? 'var(--aud)' : 'var(--text-muted)' }}>
              {done ? 'Done ✓' : isNext ? 'Next' : 'Later'}
            </span>
          </div>
        )
      })}
      {plan && Object.keys(plan.building ?? {}).length > 0 && (
        <p className="text-xs theme-text-secondary">Still to buy in later months: {Object.keys(plan.building ?? {}).map((x) => x.replace('.AX', '')).join(', ')}.</p>
      )}
      <div className="text-xs theme-text-muted space-y-1 pt-2 border-t theme-border">
        <p>Sells a stock once it drops out of the top {keepWithin}.</p>
        <p>No stop-loss or take-profit: winners are left to run.</p>
      </div>
    </section>
  )
}
