import { useState } from 'react'
import { indicatorsApi } from '../lib/api'
import { TechnicalAnalysis, RsiScreenerResult } from '../types'
import { toast } from 'sonner'
import { Search, TrendingUp, TrendingDown, Activity, AlertCircle, BarChart3, Loader2 } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'

type Market = 'asx' | 'us'

export default function StockAnalysis() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [symbol, setSymbol] = useState('')
  const [market, setMarket] = useState<Market>('asx')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null)
  const [chartData, setChartData] = useState<Record<string, unknown>[] | null>(null)
  
  const [activeTab, setActiveTab] = useState<'single' | 'screener'>('single')
  const [screenerLoading, setScreenerLoading] = useState(false)
  const [screenerResults, setScreenerResults] = useState<RsiScreenerResult[]>([])
  const [screenerSignal, setScreenerSignal] = useState<'buy' | 'sell' | 'all'>('buy')
  const [screenerStats, setScreenerStats] = useState<{total_scanned: number, signals_found: number} | null>(null)
  
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
      toast.success(`Scan complete! Found ${res.data.signals_found} signals`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Screener scan failed')
    } finally {
      setScreenerLoading(false)
    }
  }

  const handleScreenerStockClick = (sym: string) => {
    setSymbol(sym)
    setActiveTab('single')
    setAnalysis(null)
    setChartData(null)
    setTimeout(() => analyzeStock(sym), 100)
  }

  const getSignalColor = (signal: string) => {
    if (signal === 'buy') return 'text-emerald-300 bg-emerald-500/20 border border-emerald-500/30 shadow-[0_0_15px_rgba(52,211,153,0.3)]'
    if (signal === 'sell') return 'text-red-300 bg-red-500/20 border border-red-500/30 shadow-[0_0_15px_rgba(248,113,113,0.3)]'
    return 'text-amber-300 bg-amber-500/20 border border-amber-500/30 shadow-[0_0_15px_rgba(251,191,36,0.3)]'
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
          <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Stock Analysis</h1>
          <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
            Technical indicator analysis with RSI, MACD, and Bollinger Bands
          </p>
        </div>
        
        {marketSelector}
      </div>

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

      {activeTab === 'screener' && (
        <div className="space-y-6">
          <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Signal:</span>
                <div className={`inline-flex rounded-lg p-1 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
                  <button
                    onClick={() => setScreenerSignal('buy')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'buy'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Oversold (Buy)
                  </button>
                  <button
                    onClick={() => setScreenerSignal('sell')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                      screenerSignal === 'sell'
                        ? 'bg-red-500/20 text-red-300 border border-red-500/30'
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
          </div>

          {screenerLoading && (
            <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} text-center py-12`}>
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
                Found {screenerStats.signals_found} signals out of {screenerStats.total_scanned} stocks scanned
              </p>

              {screenerResults.length === 0 ? (
                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} text-center py-12`}>
                  <AlertCircle className={`w-10 h-10 mx-auto mb-4 ${isDark ? 'text-slate-500' : 'text-slate-400'}`} />
                  <p className={`text-lg font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>No signals found</p>
                  <p className={`text-sm mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    No stocks are currently showing {screenerSignal === 'buy' ? 'oversold' : screenerSignal === 'sell' ? 'overbought' : 'RSI'} signals
                  </p>
                </div>
              ) : (
                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'} overflow-hidden`}>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className={`border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
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
                            className={`border-b last:border-b-0 ${isDark ? 'border-slate-700/30 hover:bg-slate-800/50' : 'border-slate-100 hover:bg-slate-50'} cursor-pointer transition-colors`}
                            onClick={() => handleScreenerStockClick(r.symbol)}
                          >
                            <td className={`px-4 py-3 font-medium ${isDark ? 'text-sky-400' : 'text-sky-600'}`}>{r.symbol}</td>
                            <td className={`px-4 py-3 text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'} max-w-[200px] truncate`}>{r.name}</td>
                            <td className={`px-4 py-3 text-sm text-right font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                              {currencySymbol}{r.current_price.toFixed(2)}
                            </td>
                            <td className={`px-4 py-3 text-sm text-right font-bold ${
                              r.signal === 'buy' ? 'text-emerald-400' : 'text-red-400'
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

      {activeTab === 'single' && (
        <>
          <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
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
                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
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
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-0.5 bg-sky-400"></span> Price
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-0.5 bg-purple-400"></span> SMA 20
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-0.5 bg-amber-400"></span> SMA 50
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-3 h-0.5 bg-slate-500" style={{ borderTop: '1px dashed' }}></span> Bollinger
                    </span>
                  </div>
                </div>

                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>RSI (Relative Strength Index)</h2>
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
                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
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
                        <span className="flex items-center gap-1">
                          <TrendingUp className="w-4 h-4" /> Uptrend
                        </span>
                      ) : (
                        <span className="flex items-center gap-1">
                          <TrendingDown className="w-4 h-4" /> Downtrend
                        </span>
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

                <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} mb-4`}>Indicators</h2>
                  
                  <div className="space-y-4">
                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border backdrop-blur-sm`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>RSI</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          getSignalColor(analysis.indicators.rsi.signal.signal)
                        }`}>
                          {analysis.indicators.rsi.signal.signal.toUpperCase()}
                        </span>
                      </div>
                      <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{analysis.indicators.rsi.value.toFixed(1)}</p>
                      <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                        {analysis.indicators.rsi.signal.explanation}
                      </p>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border backdrop-blur-sm`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>MACD</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          getSignalColor(analysis.indicators.macd.signal.signal)
                        }`}>
                          {analysis.indicators.macd.signal.signal.toUpperCase()}
                        </span>
                      </div>
                      <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                        MACD: {analysis.indicators.macd.macd_line.toFixed(4)}
                      </p>
                      <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                        Signal: {analysis.indicators.macd.signal_line.toFixed(4)}
                      </p>
                      <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                        {analysis.indicators.macd.signal.explanation}
                      </p>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border backdrop-blur-sm`}>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>Moving Averages</span>
                      <div className="mt-2 space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>SMA 20</span>
                          <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{currencySymbol}{analysis.indicators.moving_averages.sma_20.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>SMA 50</span>
                          <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{currencySymbol}{analysis.indicators.moving_averages.sma_50.toFixed(2)}</span>
                        </div>
                        <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                          Price is {analysis.indicators.moving_averages.price_vs_sma50} SMA 50
                        </p>
                      </div>
                    </div>

                    <div className={`p-3 ${isDark ? 'bg-slate-800/50 border-slate-700/30' : 'bg-slate-100 border-slate-200'} rounded-lg border backdrop-blur-sm`}>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>Bollinger Bands</span>
                      <div className="mt-2 space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Upper</span>
                          <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{currencySymbol}{analysis.indicators.bollinger.upper.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Middle</span>
                          <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{currencySymbol}{analysis.indicators.bollinger.middle.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Lower</span>
                          <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{currencySymbol}{analysis.indicators.bollinger.lower.toFixed(2)}</span>
                        </div>
                        <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
                          Position: {analysis.indicators.bollinger.position.replace('_', ' ')}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-start gap-3 backdrop-blur-sm">
                  <AlertCircle className="w-5 h-5 text-amber-400 mt-0.5" />
                  <div>
                    <p className="text-sm text-amber-300 font-medium">Disclaimer</p>
                    <p className="text-sm text-amber-400/80 mt-1">
                      Technical analysis is for informational purposes only. 
                      Always do your own research before making investment decisions.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
