import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { indicatorsApi, stocksApi } from '../lib/api'
import { TechnicalAnalysis, RsiScreenerResult } from '../types'
import { toast } from 'sonner'
import { Search, TrendingUp, TrendingDown, Activity, AlertCircle, BarChart3, Loader2, X, ExternalLink, Users, Globe, Building2, Sparkles } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'
import HelpTooltip from '../components/HelpTooltip'

type Market = 'asx' | 'us'

interface StockDetailInfo {
  symbol: string
  name: string
  sector: string
  industry: string
  current_price: number
  market_cap: number
  description: string
  website: string
  employees: number | null
  country: string
  rsi_value?: number
  signal?: string
  strength?: string
}

export default function StockAnalysis() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const navigate = useNavigate()
  const [symbol, setSymbol] = useState('')
  const [market, setMarket] = useState<Market>('asx')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null)
  const [chartData, setChartData] = useState<Record<string, unknown>[] | null>(null)
  
  const [activeTab, setActiveTab] = useState<'single' | 'screener'>('single')
  const [screenerLoading, setScreenerLoading] = useState(false)
  const [screenerResults, setScreenerResults] = useState<RsiScreenerResult[]>([])
  const [screenerSignal, setScreenerSignal] = useState<'buy' | 'sell' | 'hold' | 'all'>('buy')
  const [screenerStats, setScreenerStats] = useState<{total_scanned: number, signals_found: number} | null>(null)
  const [selectedScannerSymbols, setSelectedScannerSymbols] = useState<Set<string>>(new Set())

  const toggleScannerSymbol = (symbol: string) => {
    setSelectedScannerSymbols((prev) => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  const toggleScannerSelectAll = () => {
    setSelectedScannerSymbols((prev) =>
      prev.size === screenerResults.length
        ? new Set()
        : new Set(screenerResults.map((r) => r.symbol))
    )
  }

  const buildPortfolioFromSelected = () => {
    if (selectedScannerSymbols.size < 2) {
      toast.error('Select at least 2 stocks to build a portfolio')
      return
    }
    const symbols = Array.from(selectedScannerSymbols)
    navigate('/manual-builder', {
      state: {
        preselectedSymbols: symbols,
        market: market === 'asx' ? 'ASX' : 'US',
        source: 'rsi-scanner',
      },
    })
  }

  // Stock detail modal
  const [detailStock, setDetailStock] = useState<StockDetailInfo | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  
  const currencySymbol = market === 'asx' ? 'A$' : '$'

  const analyzeStock = async (overrideSymbol?: string) => {
    const sym = overrideSymbol || symbol
    if (!sym) {
      toast.error('Please enter a stock symbol')
      return
    }

    setLoading(true)
    try {
      const [analysisRes, chartRes] = await Promise.all([
        indicatorsApi.analyze(sym, '1y', market),
        indicatorsApi.chartData(sym, 'all', '1y', market),
      ])
      
      setAnalysis(analysisRes.data)
      
      const dates = chartRes.data.dates
      const formattedData = dates.map((date: string, i: number) => ({
        date,
        price: chartRes.data.prices[i],
        rsi: chartRes.data.rsi?.[i],
        sma20: chartRes.data.sma_20?.[i],
        sma50: chartRes.data.sma_50?.[i],
        bbUpper: chartRes.data.bb_upper?.[i],
        bbLower: chartRes.data.bb_lower?.[i],
      }))
      
      setChartData(formattedData)
      toast.success('Analysis complete!')
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Analysis failed')
      setAnalysis(null)
      setChartData(null)
    } finally {
      setLoading(false)
    }
  }

  const runScreener = async () => {
    setScreenerLoading(true)
    setScreenerResults([])
    setScreenerStats(null)
    try {
      const res = await indicatorsApi.rsiScreener(market, screenerSignal)
      setScreenerResults(res.data.results)
      setScreenerStats({ total_scanned: res.data.total_scanned, signals_found: res.data.signals_found })
      setSelectedScannerSymbols(new Set())
      toast.success(`Scan complete! Found ${res.data.signals_found} signals`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Screener scan failed')
    } finally {
      setScreenerLoading(false)
    }
  }

  const openStockDetail = async (result: RsiScreenerResult) => {
    setDetailLoading(true)
    setDetailStock({
      symbol: result.symbol,
      name: result.name,
      sector: '',
      industry: '',
      current_price: result.current_price,
      market_cap: 0,
      description: '',
      website: '',
      employees: null,
      country: '',
      rsi_value: result.rsi_value,
      signal: result.signal,
      strength: result.strength,
    })
    try {
      const res = await stocksApi.info(result.symbol)
      setDetailStock({
        ...res.data,
        rsi_value: result.rsi_value,
        signal: result.signal,
        strength: result.strength,
      })
    } catch {
      // Keep the partial info we already have
    } finally {
      setDetailLoading(false)
    }
  }

  const goToFullAnalysis = (sym: string) => {
    const clean = sym.replace('.AX', '')
    setSymbol(clean)
    setActiveTab('single')
    setDetailStock(null)
    setAnalysis(null)
    setChartData(null)
    setTimeout(() => analyzeStock(clean), 100)
  }

  const getSignalColor = (signal: string) => {
    if (signal === 'buy') return isDark
      ? 'text-emerald-300 bg-emerald-500/20 border border-emerald-500/30'
      : 'text-emerald-700 bg-emerald-100 border border-emerald-300'
    if (signal === 'sell') return isDark
      ? 'text-red-300 bg-red-500/20 border border-red-500/30'
      : 'text-red-700 bg-red-100 border border-red-300'
    if (signal === 'hold') return isDark
      ? 'text-amber-300 bg-amber-500/20 border border-amber-500/30'
      : 'text-amber-700 bg-amber-100 border border-amber-300'
    return isDark
      ? 'text-slate-300 bg-slate-500/20 border border-slate-500/30'
      : 'text-slate-700 bg-slate-100 border border-slate-300'
  }

  const formatMarketCap = (cap: number) => {
    if (!cap) return 'N/A'
    if (cap >= 1e12) return `${(cap / 1e12).toFixed(2)}T`
    if (cap >= 1e9) return `${(cap / 1e9).toFixed(2)}B`
    if (cap >= 1e6) return `${(cap / 1e6).toFixed(2)}M`
    return cap.toLocaleString()
  }

  const tooltipStyle = {
    background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)',
    border: '1px solid rgba(148, 163, 184, 0.2)',
    borderRadius: '8px',
    color: isDark ? '#e2e8f0' : '#1e293b'
  }

  const marketSelector = (
    <div className="flex items-center gap-2">
      <span className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Market:</span>
      <div className={`inline-flex rounded-lg p-1 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
        <button
          onClick={() => { setMarket('asx'); setAnalysis(null); setChartData(null); setSymbol(''); setScreenerResults([]); setScreenerStats(null); }}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
            market === 'asx'
              ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
              : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          🇦🇺 ASX
        </button>
        <button
          onClick={() => { setMarket('us'); setAnalysis(null); setChartData(null); setSymbol(''); setScreenerResults([]); setScreenerStats(null); }}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
            market === 'us'
              ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
              : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          🇺🇸 S&P 500
        </button>
      </div>
    </div>
  )

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className={`text-2xl sm:text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Stock Analysis</h1>
          <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1 flex items-center flex-wrap gap-x-0`}>
            Technical indicator analysis with
            <span className="inline-flex items-center mx-1">RSI<HelpTooltip term="RSI" /></span>,
            <span className="inline-flex items-center mx-1">MACD<HelpTooltip term="MACD" /></span>, and
            <span className="inline-flex items-center mx-1">Bollinger Bands<HelpTooltip term="Bollinger Bands" /></span>
          </p>
        </div>
        {marketSelector}
      </div>

      {/* Tab selector */}
      <div className={`inline-flex rounded-lg p-1 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
        <button
          onClick={() => setActiveTab('single')}
          className={`px-5 py-2.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
            activeTab === 'single'
              ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
              : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          <Search className="w-4 h-4" />
          Single Stock
        </button>
        <button
          onClick={() => setActiveTab('screener')}
          className={`px-5 py-2.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${
            activeTab === 'screener'
              ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
              : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          RSI Screener
        </button>
      </div>

      {/* ── RSI SCREENER TAB ── */}
      {activeTab === 'screener' && (
        <div className="space-y-6">
          <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Signal:</span>
                <div className={`inline-flex rounded-lg p-1 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
                  <button
                    onClick={() => setScreenerSignal('buy')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'buy'
                        ? isDark ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                        : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Oversold (Buy)
                  </button>
                  <button
                    onClick={() => setScreenerSignal('hold')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'hold'
                        ? isDark ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-amber-100 text-amber-700 border border-amber-300'
                        : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Neutral (Hold)
                  </button>
                  <button
                    onClick={() => setScreenerSignal('sell')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'sell'
                        ? isDark ? 'bg-red-500/20 text-red-300 border border-red-500/30' : 'bg-red-100 text-red-700 border border-red-300'
                        : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Overbought (Sell)
                  </button>
                  <button
                    onClick={() => setScreenerSignal('all')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'all'
                        ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
                        : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    All Signals
                  </button>
                </div>
              </div>
              <button
                onClick={runScreener}
                disabled={screenerLoading}
                className="btn-primary flex items-center gap-2"
              >
                {screenerLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Activity className="w-5 h-5" />}
                {screenerLoading ? 'Scanning...' : 'Scan'}
              </button>
            </div>

            {/* Signal explanation */}
            <div className={`mt-3 p-3 rounded-lg text-sm ${isDark ? 'bg-slate-800/50 text-slate-400' : 'bg-slate-50 text-slate-600'}`}>
              {screenerSignal === 'buy' && '🟢 Oversold stocks (RSI ≤ 30) — potential buying opportunities where the stock may be undervalued'}
              {screenerSignal === 'hold' && '🟡 Neutral stocks (RSI 30–70) — currently fairly valued with no strong directional signal'}
              {screenerSignal === 'sell' && '🔴 Overbought stocks (RSI ≥ 70) — potential selling opportunities where the stock may be overvalued'}
              {screenerSignal === 'all' && '📊 All signals combined — buy (RSI ≤ 30), hold (RSI 30–70), and sell (RSI ≥ 70) signals'}
            </div>
          </div>

          {screenerLoading && (
            <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} text-center py-12`}>
              <Loader2 className={`w-10 h-10 animate-spin mx-auto mb-4 ${isDark ? 'text-sky-400' : 'text-sky-600'}`} />
              <p className={`text-lg font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                Scanning {market === 'asx' ? 'ASX 200' : 'S&P 500'} stocks...
              </p>
              <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                This may take a minute
              </p>
            </div>
          )}

          {!screenerLoading && screenerStats && (
            <div className="space-y-4">
              <p className={`text-sm font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                Found <strong>{screenerStats.signals_found}</strong> signals out of {screenerStats.total_scanned} stocks scanned
                {screenerSignal === 'hold' && <span className={`ml-2 text-xs ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>— click any row to see company details</span>}
              </p>

              {screenerResults.length === 0 ? (
                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} text-center py-12`}>
                  <AlertCircle className={`w-10 h-10 mx-auto mb-4 ${isDark ? 'text-slate-500' : 'text-slate-400'}`} />
                  <p className={`text-lg font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>No signals found</p>
                  <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    No stocks are currently showing {screenerSignal === 'buy' ? 'oversold' : screenerSignal === 'sell' ? 'overbought' : screenerSignal === 'hold' ? 'neutral' : 'RSI'} signals
                  </p>
                </div>
              ) : (
                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} overflow-hidden`}>
                  {selectedScannerSymbols.size > 0 && (
                    <div className={`flex items-center justify-between px-4 py-3 border-b ${isDark ? 'border-slate-700/50 bg-slate-800/40' : 'border-slate-200 bg-sky-50'}`}>
                      <div className={`text-sm ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                        <strong>{selectedScannerSymbols.size}</strong> stock{selectedScannerSymbols.size === 1 ? '' : 's'} selected
                        {selectedScannerSymbols.size < 2 && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-amber-300' : 'text-amber-600'}`}>(need at least 2)</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setSelectedScannerSymbols(new Set())}
                          className={`text-xs px-3 py-1.5 rounded transition-colors ${isDark ? 'text-slate-300 hover:bg-slate-700/50' : 'text-slate-600 hover:bg-slate-200'}`}
                        >
                          Clear
                        </button>
                        <button
                          onClick={buildPortfolioFromSelected}
                          disabled={selectedScannerSymbols.size < 2}
                          className="btn-primary flex items-center gap-2 text-sm py-1.5 px-3 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Sparkles className="w-4 h-4" />
                          Build Portfolio ({selectedScannerSymbols.size})
                        </button>
                      </div>
                    </div>
                  )}
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className={`border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                          <th className={`px-3 py-3 w-10 text-center`}>
                            <input
                              type="checkbox"
                              aria-label="Select all"
                              checked={screenerResults.length > 0 && selectedScannerSymbols.size === screenerResults.length}
                              onChange={toggleScannerSelectAll}
                              className="cursor-pointer accent-sky-500"
                            />
                          </th>
                          <th className={`text-left px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Symbol</th>
                          <th className={`text-left px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Name</th>
                          <th className={`text-right px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Price</th>
                          <th className={`text-right px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>RSI</th>
                          <th className={`text-center px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Signal</th>
                          <th className={`text-center px-4 py-3 text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Strength</th>
                        </tr>
                      </thead>
                      <tbody>
                        {screenerResults.map((r) => (
                          <tr
                            key={r.symbol}
                            className={`border-b last:border-b-0 ${isDark ? 'border-slate-700/30 hover:bg-slate-800/50' : 'border-slate-100 hover:bg-slate-50'} cursor-pointer transition-colors ${selectedScannerSymbols.has(r.symbol) ? (isDark ? 'bg-sky-900/20' : 'bg-sky-50/60') : ''}`}
                            onClick={() => openStockDetail(r)}
                          >
                            <td
                              className="px-3 py-3 text-center"
                              onClick={(e) => { e.stopPropagation(); toggleScannerSymbol(r.symbol) }}
                            >
                              <input
                                type="checkbox"
                                aria-label={`Select ${r.symbol}`}
                                checked={selectedScannerSymbols.has(r.symbol)}
                                onChange={(e) => { e.stopPropagation(); toggleScannerSymbol(r.symbol) }}
                                onClick={(e) => e.stopPropagation()}
                                className="cursor-pointer accent-sky-500"
                              />
                            </td>
                            <td className={`px-4 py-3 font-medium ${isDark ? 'text-sky-400' : 'text-sky-600'}`}>
                              {r.symbol.replace('.AX', '')}
                            </td>
                            <td className={`px-4 py-3 text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'} max-w-[200px] truncate`}>{r.name}</td>
                            <td className={`px-4 py-3 text-sm text-right font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                              {currencySymbol}{r.current_price.toFixed(2)}
                            </td>
                            <td className={`px-4 py-3 text-sm text-right font-bold ${
                              r.signal === 'buy' ? 'text-emerald-400' : r.signal === 'sell' ? 'text-red-400' : 'text-amber-400'
                            }`}>
                              {r.rsi_value.toFixed(1)}
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getSignalColor(r.signal)}`}>
                                {r.signal.toUpperCase()}
                              </span>
                            </td>
                            <td className={`px-4 py-3 text-center text-sm capitalize ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                              {r.strength}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── SINGLE STOCK TAB ── */}
      {activeTab === 'single' && (
        <>
          <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
            <div className="flex gap-4">
              <div className="flex-1 relative">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && analyzeStock()}
                  placeholder={market === 'asx'
                    ? "Enter ASX stock symbol (e.g., BHP, CBA, CSL)"
                    : "Enter US stock symbol (e.g., AAPL, MSFT, GOOGL)"}
                  className={`input pl-10 ${isDark ? 'bg-slate-800/70 border-slate-600/50 text-slate-100' : 'bg-white border-slate-300 text-slate-900'} placeholder-slate-500`}
                />
              </div>
              <button
                onClick={() => analyzeStock()}
                disabled={loading}
                className="btn-primary flex items-center gap-2"
              >
                <Activity className="w-5 h-5" />
                {loading ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>

          {analysis && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Price Chart</h2>
                  {chartData && (
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={chartData}>
                        <CartesianGrid stroke={isDark ? '#334155' : '#e2e8f0'} strokeDasharray="3 3" opacity={0.3} />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }}
                          stroke={isDark ? '#64748b' : '#94a3b8'}
                          tickFormatter={(value) => new Date(value).toLocaleDateString('en-AU', { month: 'short' })}
                        />
                        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }} stroke={isDark ? '#64748b' : '#94a3b8'} />
                        <Tooltip
                          contentStyle={tooltipStyle}
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value: number) => [`${currencySymbol}${value?.toFixed(2) || 'N/A'}`, '']}
                        />
                        <Line type="monotone" dataKey="price" stroke="#38bdf8" strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="sma20" stroke="#a78bfa" strokeWidth={1} dot={false} opacity={0.8} />
                        <Line type="monotone" dataKey="sma50" stroke="#fbbf24" strokeWidth={1} dot={false} opacity={0.8} />
                        <Line type="monotone" dataKey="bbUpper" stroke="#64748b" strokeWidth={1} dot={false} strokeDasharray="5 5" />
                        <Line type="monotone" dataKey="bbLower" stroke="#64748b" strokeWidth={1} dot={false} strokeDasharray="5 5" />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                  <div className={`flex gap-4 mt-4 text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-sky-400 inline-block"></span> Price</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-purple-400 inline-block"></span> SMA 20</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-amber-400 inline-block"></span> SMA 50</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-slate-500 inline-block"></span> Bollinger</span>
                  </div>
                </div>

                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4 flex items-center`}>RSI (Relative Strength Index)<HelpTooltip term="RSI" /></h2>
                  {chartData && (
                    <ResponsiveContainer width="100%" height={150}>
                      <LineChart data={chartData}>
                        <CartesianGrid stroke={isDark ? '#334155' : '#e2e8f0'} strokeDasharray="3 3" opacity={0.3} />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }}
                          stroke={isDark ? '#64748b' : '#94a3b8'}
                          tickFormatter={(value) => new Date(value).toLocaleDateString('en-AU', { month: 'short' })}
                        />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }} stroke={isDark ? '#64748b' : '#94a3b8'} />
                        <Tooltip
                          contentStyle={tooltipStyle}
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value: number) => [value?.toFixed(2) || 'N/A', 'RSI']}
                        />
                        <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
                        <ReferenceLine y={30} stroke="#34d399" strokeDasharray="3 3" />
                        <Line type="monotone" dataKey="rsi" stroke="#818cf8" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                  <div className={`flex gap-4 mt-2 text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    <span>Above 70: Overbought (Sell signal)</span>
                    <span>Below 30: Oversold (Buy signal)</span>
                  </div>
                </div>
              </div>

              <div className="space-y-6">
                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                      {market === 'asx' ? analysis.symbol.replace('.AX', '') : analysis.symbol}
                    </h2>
                    <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                      analysis.trend === 'uptrend'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-red-500/20 text-red-300 border border-red-500/30'
                    }`}>
                      {analysis.trend === 'uptrend' ? (
                        <span className="flex items-center gap-1"><TrendingUp className="w-4 h-4" /> Uptrend</span>
                      ) : (
                        <span className="flex items-center gap-1"><TrendingDown className="w-4 h-4" /> Downtrend</span>
                      )}
                    </span>
                  </div>

                  <p className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>
                    {currencySymbol}{analysis.current_price.toFixed(2)}
                  </p>

                  <div className={`p-4 rounded-lg ${getSignalColor(analysis.overall_signal)}`}>
                    <p className="font-semibold capitalize">
                      Overall Signal: {analysis.overall_signal.toUpperCase()}
                    </p>
                  </div>
                </div>

                <div className={`card ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Indicators</h2>
                  <div className="space-y-4">
                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border`}>
                      <div className="flex justify-between items-center">
                        <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'} flex items-center`}>RSI<HelpTooltip term="RSI" /></span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${getSignalColor(analysis.indicators.rsi.signal.signal)}`}>
                          {analysis.indicators.rsi.signal.signal.toUpperCase()}
                        </span>
                      </div>
                      <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{analysis.indicators.rsi.value.toFixed(1)}</p>
                      <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{analysis.indicators.rsi.signal.explanation}</p>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border`}>
                      <div className="flex justify-between items-center">
                        <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'} flex items-center`}>MACD<HelpTooltip term="MACD" /></span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${getSignalColor(analysis.indicators.macd.signal.signal)}`}>
                          {analysis.indicators.macd.signal.signal.toUpperCase()}
                        </span>
                      </div>
                      <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{analysis.indicators.macd.signal.explanation}</p>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border`}>
                      <div className="flex justify-between items-center">
                        <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'} flex items-center`}>Bollinger Bands<HelpTooltip term="Bollinger Bands" /></span>
                      </div>
                      <p className={`text-sm mt-1 capitalize ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{analysis.indicators.bollinger.position}</p>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border`}>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>Moving Averages</span>
                      <div className="mt-2 space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>vs SMA 20</span>
                          <span className={analysis.indicators.moving_averages.price_vs_sma20 === 'above' ? 'text-emerald-400' : 'text-red-400'}>
                            {analysis.indicators.moving_averages.price_vs_sma20}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>vs SMA 50</span>
                          <span className={analysis.indicators.moving_averages.price_vs_sma50 === 'above' ? 'text-emerald-400' : 'text-red-400'}>
                            {analysis.indicators.moving_averages.price_vs_sma50}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── STOCK DETAIL MODAL ── */}
      {detailStock && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div
            className="rounded-2xl w-full max-w-lg border overflow-hidden"
            style={{
              background: isDark ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.98)',
              borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)',
              boxShadow: isDark ? '0 8px 40px rgba(0,0,0,0.6)' : '0 8px 40px rgba(0,0,0,0.15)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            {/* Header */}
            <div className={`flex items-start justify-between p-5 border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
              <div>
                <div className="flex items-center gap-3">
                  <h2 className={`text-xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                    {detailStock.symbol.replace('.AX', '')}
                  </h2>
                  {detailStock.signal && (
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getSignalColor(detailStock.signal)}`}>
                      {detailStock.signal.toUpperCase()}
                    </span>
                  )}
                </div>
                <p className={`mt-1 text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>{detailStock.name}</p>
              </div>
              <button
                onClick={() => setDetailStock(null)}
                className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-slate-700 text-slate-400' : 'hover:bg-slate-100 text-slate-600'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 space-y-4">
              {/* Price + RSI */}
              <div className="grid grid-cols-3 gap-3">
                <div className={`p-3 rounded-xl border ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Price</p>
                  <p className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                    {currencySymbol}{detailStock.current_price.toFixed(2)}
                  </p>
                </div>
                {detailStock.rsi_value != null && (
                  <div className={`p-3 rounded-xl border ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>RSI (3mo)</p>
                    <p className={`text-lg font-bold ${
                      detailStock.signal === 'buy' ? 'text-emerald-400' : detailStock.signal === 'sell' ? 'text-red-400' : 'text-amber-400'
                    }`}>{detailStock.rsi_value.toFixed(1)}</p>
                  </div>
                )}
                {detailStock.market_cap > 0 && (
                  <div className={`p-3 rounded-xl border ${isDark ? 'bg-slate-800/50 border-slate-700/50' : 'bg-slate-50 border-slate-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Mkt Cap</p>
                    <p className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{formatMarketCap(detailStock.market_cap)}</p>
                  </div>
                )}
              </div>

              {/* Sector / Industry */}
              {detailLoading && (
                <div className="flex items-center gap-2 py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-sky-400" />
                  <span className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>Loading company details...</span>
                </div>
              )}

              {!detailLoading && (detailStock.sector || detailStock.industry) && (
                <div className="flex flex-wrap gap-2">
                  {detailStock.sector && detailStock.sector !== 'Unknown' && (
                    <span className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs border ${isDark ? 'bg-sky-500/10 border-sky-500/20 text-sky-300' : 'bg-sky-50 border-sky-200 text-sky-700'}`}>
                      <Building2 className="w-3 h-3" />{detailStock.sector}
                    </span>
                  )}
                  {detailStock.industry && detailStock.industry !== 'Unknown' && (
                    <span className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs border ${isDark ? 'bg-purple-500/10 border-purple-500/20 text-purple-300' : 'bg-purple-50 border-purple-200 text-purple-700'}`}>
                      {detailStock.industry}
                    </span>
                  )}
                  {detailStock.country && (
                    <span className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs border ${isDark ? 'bg-slate-700 border-slate-600 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'}`}>
                      <Globe className="w-3 h-3" />{detailStock.country}
                    </span>
                  )}
                  {detailStock.employees && (
                    <span className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs border ${isDark ? 'bg-slate-700 border-slate-600 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'}`}>
                      <Users className="w-3 h-3" />{detailStock.employees.toLocaleString()} employees
                    </span>
                  )}
                </div>
              )}

              {/* Strength */}
              {detailStock.strength && (
                <div className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-slate-800/50 border-slate-700/30 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-700'}`}>
                  Signal strength: <span className="font-medium capitalize">{detailStock.strength}</span>
                </div>
              )}

              {/* Description */}
              {!detailLoading && detailStock.description && (
                <div>
                  <h3 className={`text-sm font-semibold mb-2 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>About this company</h3>
                  <p className={`text-sm leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    {detailStock.description.length > 600
                      ? detailStock.description.slice(0, 600) + '...'
                      : detailStock.description}
                  </p>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => goToFullAnalysis(detailStock.symbol)}
                  className="btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  <Activity className="w-4 h-4" />
                  Full Analysis
                </button>
                {detailStock.website && (
                  <a
                    href={detailStock.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`px-4 py-2 rounded-lg border text-sm font-medium flex items-center gap-2 transition-colors ${
                      isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-slate-300 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <ExternalLink className="w-4 h-4" />
                    Website
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
