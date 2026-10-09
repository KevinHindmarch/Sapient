import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { portfolioApi, stocksApi, brokerApi, aiApi, apiErrorMessage, money, PortfolioSummary, RebalancePlan } from '../lib/api'
import { Portfolio, Position, Transaction } from '../types'
import { toast } from 'sonner'
import { ArrowLeft, TrendingUp, TrendingDown, DollarSign, Pencil, Trash2, Plus, X, Search, RefreshCw, Sparkles, Send, Zap, Activity, Link2, AlertTriangle } from 'lucide-react'
import HelpTooltip from '../components/HelpTooltip'
import BrokerCompareCard from '../components/BrokerCompareCard'
import { format } from 'date-fns'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts'
import { differenceInDays } from 'date-fns'
import { useTheme } from '../lib/theme'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

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
      toast.error(err.response?.data?.detail || 'Failed to update AI mode')
    } finally {
      setSavingAiMode(false)
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
      setAiMode(response.data.portfolio?.ai_mode || 'off')

      const symbols = response.data.positions.map((p: Position) => p.symbol)
      if (symbols.length > 0) {
        loadCurrentPrices(symbols)
      }
    } catch (error) {
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
      toast.error(err.response?.data?.detail || 'Failed to update position')
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
      toast.error(err.response?.data?.detail || 'Failed to remove position')
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
      toast.error(err.response?.data?.detail || 'Failed to add stock')
    } finally {
      setSaving(false)
    }
  }

  const tooltipStyle = {
    backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)',
    border: `1px solid ${isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)'}`,
    borderRadius: '12px',
    boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.4)' : '0 8px 32px rgba(0, 0, 0, 0.1)',
    backdropFilter: 'blur(12px)',
    color: isDark ? '#f1f5f9' : '#0f172a'
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

  const chartData = positions
    .filter((p) => p.status === 'active')
    .map((p) => ({
      name: p.symbol.replace('.AX', ''),
      value: Number(p.allocation_amount) || 0,
    }))

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

  const generateGrowthData = () => {
    const initial = Number(portfolio.initial_investment)
    const expectedReturn = Number(portfolio.expected_return || 0.10)
    const createdAt = new Date(portfolio.created_at)
    const today = new Date()
    const daysSinceCreation = Math.max(differenceInDays(today, createdAt), 1)
    
    const minProjectionDays = 365
    const projectionDays = Math.max(daysSinceCreation, minProjectionDays)
    
    const dataPoints: { date: string; expected: number; actual: number | null }[] = []
    
    const snapshotMap = new Map<string, number>()
    if (data?.snapshots) {
      data.snapshots.forEach((s: Record<string, unknown>) => {
        const dateStr = format(new Date(s.snapshot_date as string), 'MMM d, yyyy')
        snapshotMap.set(dateStr, Number(s.total_value))
      })
    }
    
    const dailyRate = expectedReturn / 365
    const numPoints = 12
    const interval = Math.max(1, Math.floor(projectionDays / numPoints))
    
    for (let i = 0; i <= projectionDays; i += interval) {
      const date = new Date(createdAt)
      date.setDate(date.getDate() + i)
      const dateStr = format(date, 'MMM d, yyyy')
      const shortDate = format(date, 'MMM yyyy')
      
      const expectedValue = initial * (1 + dailyRate * i)
      
      let actualValue: number | null = null
      if (i <= daysSinceCreation) {
        actualValue = snapshotMap.get(dateStr) || null
        if (i === 0) actualValue = initial
      }
      
      dataPoints.push({
        date: shortDate,
        expected: Math.round(expectedValue),
        actual: actualValue
      })
    }
    
    const todayIdx = dataPoints.findIndex((_, idx) => {
      const dayOffset = idx * interval
      return dayOffset >= daysSinceCreation
    })
    
    if (todayIdx > 0 && todayIdx < dataPoints.length) {
      dataPoints[todayIdx].actual = Math.round(totalValue)
    } else if (dataPoints.length > 1) {
      dataPoints[1].actual = Math.round(totalValue)
    }
    
    return dataPoints
  }

  const growthChartData = generateGrowthData()
  
  const chartYDomain = (() => {
    const values = growthChartData.flatMap(d => [d.expected, d.actual].filter(v => v !== null)) as number[]
    if (values.length === 0) return [0, 100000]
    const min = Math.min(...values)
    const max = Math.max(...values)
    const padding = (max - min) * 0.1 || max * 0.1
    return [Math.floor((min - padding) / 1000) * 1000, Math.ceil((max + padding) / 1000) * 1000]
  })()

  const gridStroke = isDark ? '#334155' : '#e2e8f0'
  const axisStroke = isDark ? '#475569' : '#94a3b8'
  const tickFill = isDark ? '#94a3b8' : '#64748b'
  const legendColor = isDark ? '#94a3b8' : '#64748b'

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Link to="/portfolios" className={`p-2 mt-1 ${isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-100'} rounded-lg transition-colors border border-transparent ${isDark ? 'hover:border-slate-700/50' : 'hover:border-slate-200'} shrink-0`}>
            <ArrowLeft className={`w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
          </Link>
          <div>
            <h1 className={`text-2xl sm:text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{portfolio.name}</h1>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
                portfolio.mode === 'auto' 
                  ? isDark ? 'bg-purple-500/20 text-purple-300 border-purple-500/30' : 'bg-purple-100 text-purple-700 border-purple-300'
                  : isDark ? 'bg-sky-500/20 text-sky-300 border-sky-500/30' : 'bg-sky-100 text-sky-700 border-sky-300'
              }`}>
                {portfolio.mode === 'auto' ? 'Auto' : 'Manual'}
              </span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
                portfolio.risk_tolerance === 'conservative'
                  ? isDark ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-emerald-100 text-emerald-700 border-emerald-300'
                  : portfolio.risk_tolerance === 'aggressive'
                  ? isDark ? 'bg-red-500/20 text-red-300 border-red-500/30' : 'bg-red-100 text-red-700 border-red-300'
                  : isDark ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' : 'bg-amber-100 text-amber-700 border-amber-300'
              }`}>
                {portfolio.risk_tolerance}
              </span>
              <span className="hidden sm:inline text-sm text-slate-500">
                Created {format(new Date(portfolio.created_at), 'MMM d, yyyy')}
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            onClick={handleSyncBroker}
            disabled={syncingBroker}
            title={brokerConnected ? `Sync with IBKR (${brokerEnv})` : 'Connect IBKR first'}
            className={`flex items-center gap-1.5 px-3 py-2 sm:px-4 sm:py-2.5 rounded-xl border font-medium transition-all duration-200 text-sm disabled:opacity-50 ${
              brokerConnected
                ? isDark
                  ? 'bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 border-sky-500/30 hover:border-sky-500/50'
                  : 'bg-sky-50 hover:bg-sky-100 text-sky-700 border-sky-200 hover:border-sky-300'
                : isDark
                ? 'bg-slate-800/50 text-slate-500 border-slate-700/50'
                : 'bg-slate-100 text-slate-500 border-slate-200'
            }`}
          >
            {syncingBroker ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button
            onClick={openRebalanceDrawer}
            className="flex items-center gap-1.5 px-3 py-2 sm:px-4 sm:py-2.5 bg-gradient-to-r from-emerald-500/15 to-sky-500/15 hover:from-emerald-500/25 hover:to-sky-500/25 text-emerald-400 hover:text-emerald-300 rounded-xl border border-emerald-500/30 hover:border-emerald-500/50 font-medium transition-all duration-200 text-sm"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">Rebalance</span>
          </button>
          <button
            onClick={() => setShowDeletePortfolioModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 sm:px-4 sm:py-2.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 rounded-xl border border-red-500/20 hover:border-red-500/40 font-medium transition-all duration-200 text-sm"
          >
            <Trash2 className="w-4 h-4" />
            <span className="hidden sm:inline">Delete</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-primary flex items-center gap-2 text-sm disabled:opacity-50"
            disabled={atBroker}
            title={atBroker ? 'This portfolio follows your IBKR fills; buy more with an order instead' : undefined}
          >
            <Plus className="w-4 h-4 sm:w-5 sm:h-5" />
            <span>Add Stock</span>
          </button>
        </div>
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

      {/* Live price loading banner */}
      {loadingPrices && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
          isDark
            ? 'bg-sky-500/10 border-sky-500/30 text-sky-300'
            : 'bg-sky-50 border-sky-200 text-sky-700'
        }`}>
          <RefreshCw className="w-4 h-4 animate-spin shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Fetching live prices…</p>
            {priceProgress.total > 0 && (
              <div className="flex items-center gap-2 mt-1">
                <div className={`flex-1 h-1.5 rounded-full ${isDark ? 'bg-slate-700' : 'bg-sky-100'}`}>
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-500"
                    style={{ width: `${(priceProgress.done / priceProgress.total) * 100}%` }}
                  />
                </div>
                <span className="text-xs shrink-0 tabular-nums">
                  {priceProgress.done} / {priceProgress.total}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {summary && summary.prices_missing.length > 0 && (
        <p className="text-sm text-amber-600 flex items-center gap-2" data-testid="prices-missing">
          <AlertTriangle className="w-4 h-4" /> No current price for {summary.prices_missing.join(', ')} (Yahoo didn't answer).
          Those holdings are valued at what they cost until a price comes back.
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4" data-testid="portfolio-money">
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Money put in</p>
          <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            {summary ? money(summary.money_put_in, summary.currency, 0) : `$${costBasis.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          </p>
          <p className="text-xs theme-text-muted">Holdings cost {summary ? money(summary.cost_of_holdings, summary.currency, 0) : '…'}</p>
        </div>
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Value now (incl. cash)</p>
          {loadingPrices ? (
            <div className="mt-2 space-y-1.5">
              <div className="animate-pulse h-8 w-28 rounded-lg bg-slate-500/20" />
              <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Loading live data…</p>
            </div>
          ) : (
            <>
              <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {summary ? money(summary.total_value, summary.currency, 0) : `$${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              </p>
              {summary && <p className="text-xs theme-text-muted">Shares {money(summary.market_value, summary.currency, 0)}</p>}
            </>
          )}
        </div>
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Total Return</p>
          {loadingPrices ? (
            <div className="mt-2 space-y-1.5">
              <div className="animate-pulse h-8 w-24 rounded-lg bg-slate-500/20" />
              <p className={`text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Loading live data…</p>
            </div>
          ) : (
            <p className={`text-2xl font-bold flex items-center gap-1 ${
              totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'
            }`} style={{ textShadow: totalReturn >= 0 ? '0 0 15px rgba(52, 211, 153, 0.4)' : '0 0 15px rgba(248, 113, 113, 0.4)' }}>
              {totalReturn >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
              {totalReturn >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
            </p>
          )}
          {summary && !loadingPrices && (
            <p className="text-xs theme-text-muted">
              {money(summary.total_return, summary.currency, 0)} · sold {money(summary.realised_pnl, summary.currency, 0)}
              {summary.fees > 0 ? ` · fees ${money(summary.fees, summary.currency, 0)}` : ''}
            </p>
          )}
        </div>
        <div className="card">
          <p className={`text-sm flex items-center ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Cash</p>
          <p className={`text-2xl font-bold ${summary && summary.cash < 0 ? 'text-red-500' : isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            {summary ? money(summary.cash, summary.currency, 0) : '…'}
          </p>
          <p className="text-xs theme-text-muted">Not yet invested, or from sales</p>
        </div>
      </div>

      <div className="card">
        <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Portfolio Growth</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={growthChartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis 
              dataKey="date" 
              tick={{ fontSize: 12, fill: tickFill }}
              tickLine={{ stroke: axisStroke }}
              axisLine={{ stroke: axisStroke }}
            />
            <YAxis 
              tick={{ fontSize: 12, fill: tickFill }}
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              tickLine={{ stroke: axisStroke }}
              axisLine={{ stroke: axisStroke }}
              domain={chartYDomain}
            />
            <Tooltip 
              formatter={(value: number, name: string) => [
                `$${value.toLocaleString()}`,
                name === 'expected' ? 'Expected' : 'Actual'
              ]}
              contentStyle={tooltipStyle}
              labelStyle={{ color: legendColor }}
            />
            <Legend 
              formatter={(value) => <span style={{ color: legendColor }}>{value === 'expected' ? 'Expected Growth' : 'Actual Growth'}</span>}
            />
            <Line 
              type="monotone" 
              dataKey="expected" 
              stroke="#64748b" 
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              name="expected"
            />
            <Line 
              type="monotone" 
              dataKey="actual" 
              stroke="#10b981" 
              strokeWidth={3}
              dot={{ fill: '#10b981', strokeWidth: 2, r: 4 }}
              connectNulls
              name="actual"
            />
          </LineChart>
        </ResponsiveContainer>
        <div className="flex justify-center gap-6 mt-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-8 h-0.5 bg-slate-500" style={{ backgroundImage: 'repeating-linear-gradient(90deg, #64748b 0, #64748b 5px, transparent 5px, transparent 10px)' }}></div>
            <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Expected ({((portfolio.expected_return || 0.10) * 100).toFixed(1)}% p.a.)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-0.5 bg-emerald-500"></div>
            <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Actual ({totalReturnPct >= 0 ? '+' : ''}{totalReturnPct.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card">
          <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Positions</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={`text-left text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'} border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                  <th className="pb-3 font-medium">Symbol</th>
                  <th className="pb-3 font-medium">Quantity</th>
                  <th className="pb-3 font-medium">Avg Cost</th>
                  <th className="pb-3 font-medium">Current</th>
                  <th className="pb-3 font-medium">Value</th>
                  <th className="pb-3 font-medium">P/L</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {positions.filter(p => p.status === 'active').map((position) => {
                  const priceMissing = !currentPrices[position.symbol]
                  const currentPrice = currentPrices[position.symbol] || Number(position.avg_cost)
                  const marketValue = currentPrice * Number(position.quantity)
                  const costBasis = Number(position.avg_cost) * Number(position.quantity)
                  const pl = marketValue - costBasis
                  const plPct = costBasis > 0 ? (pl / costBasis) * 100 : 0

                  return (
                    <tr key={position.id} className={`border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'} last:border-b-0 ${isDark ? 'bg-slate-800/30 hover:bg-slate-700/30' : 'bg-slate-50 hover:bg-slate-100'} transition-colors`}>
                      <td className={`py-3 font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{position.symbol.replace('.AX', '')}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                        {atBroker ? Number(position.quantity).toFixed(0) : Number(position.quantity).toFixed(2)}
                        {atBroker && position.planned_quantity != null && Number(position.quantity) < Number(position.planned_quantity) && (
                          <span className="block text-xs text-amber-600">of {Number(position.planned_quantity)} planned</span>
                        )}
                      </td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>${Number(position.avg_cost).toFixed(2)}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                        {priceMissing && !loadingPrices ? <span className="text-amber-600" title="No current price from Yahoo">n/a</span> : `$${currentPrice.toFixed(2)}`}
                      </td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>${marketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td className={`py-3 font-medium ${pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`} style={{ textShadow: pl >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                        {pl >= 0 ? '+' : ''}{plPct.toFixed(2)}%
                      </td>
                      <td className="py-3 text-right">
                        {atBroker ? <span className="text-xs theme-text-muted">at IBKR</span> : (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => openEditModal(position)}
                            className={`p-1.5 ${isDark ? 'text-slate-400' : 'text-slate-600'} hover:text-sky-400 hover:bg-sky-500/20 rounded transition-colors`}
                            title="Edit position"
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => openDeleteModal(position)}
                            className={`p-1.5 ${isDark ? 'text-slate-400' : 'text-slate-600'} hover:text-red-400 hover:bg-red-500/20 rounded transition-colors`}
                            title="Remove position"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Allocation</h2>
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                >
                  {chartData.map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  formatter={(value: number) => `$${value.toLocaleString()}`}
                  contentStyle={tooltipStyle}
                />
                <Legend 
                  formatter={(value) => <span style={{ color: legendColor }}>{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {id && <BrokerCompareCard portfolioId={Number(id)} />}

      <div className="card">
        <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Recent Transactions</h2>
        {transactions.length === 0 ? (
          <p className="text-slate-500 text-center py-4">No transactions yet</p>
        ) : (
          <div className="space-y-3">
            {transactions.slice(0, 10).map((txn) => (
              <div key={txn.id} className={`flex items-center justify-between p-3 ${isDark ? 'bg-slate-800/30' : 'bg-slate-50'} rounded-lg border ${isDark ? 'border-slate-700/50' : 'border-slate-200'} ${isDark ? 'hover:bg-slate-700/30' : 'hover:bg-slate-100'} transition-colors`}>
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded border ${
                    txn.txn_type === 'buy' ? 'bg-emerald-500/20 border-emerald-500/30' : 'bg-red-500/20 border-red-500/30'
                  }`}>
                    <DollarSign className={`w-4 h-4 ${
                      txn.txn_type === 'buy' ? 'text-emerald-400' : 'text-red-400'
                    }`} />
                  </div>
                  <div>
                    <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                      {txn.txn_type.toUpperCase()} {txn.symbol.replace('.AX', '')}
                    </p>
                    <p className="text-sm text-slate-500">
                      {Number(txn.quantity).toFixed(2)} @ ${Number(txn.price).toFixed(2)}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>${Number(txn.total_amount).toLocaleString()}</p>
                  <p className="text-sm text-slate-500">
                    {format(new Date(txn.txn_time), 'MMM d, h:mm a')}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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
