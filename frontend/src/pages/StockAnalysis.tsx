import { useState } from 'react'
import { indicatorsApi } from '../lib/api'
import { TechnicalAnalysis } from '../types'
import { toast } from 'sonner'
import { Search, TrendingUp, TrendingDown, Activity, AlertCircle } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid } from 'recharts'
import { useTheme } from '../lib/theme'

export default function StockAnalysis() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const [symbol, setSymbol] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null)
  const [chartData, setChartData] = useState<Record<string, unknown>[] | null>(null)

  const analyzeStock = async () => {
    if (!symbol) {
      toast.error('Please enter a stock symbol')
      return
    }

    setLoading(true)
    try {
      const [analysisRes, chartRes] = await Promise.all([
        indicatorsApi.analyze(symbol),
        indicatorsApi.chartData(symbol),
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

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Stock Analysis</h1>
        <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1`}>
          Technical indicator analysis with RSI, MACD, and Bollinger Bands
        </p>
      </div>

      <div className={`card backdrop-blur-xl ${isDark ? 'bg-slate-900/60 border-slate-700/50' : 'bg-white border-slate-300'}`}>
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && analyzeStock()}
              placeholder="Enter ASX stock symbol (e.g., BHP, CBA, CSL)"
              className={`input pl-10 ${isDark ? 'bg-slate-800/70 border-slate-600/50 text-slate-100' : 'bg-white border-slate-300 text-slate-900'} placeholder-slate-500`}
            />
          </div>
          <button
            onClick={analyzeStock}
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
                      formatter={(value: number) => [`$${value?.toFixed(2) || 'N/A'}`, '']}
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
                  {analysis.symbol.replace('.AX', '')}
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
                ${analysis.current_price.toFixed(2)}
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
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>${analysis.indicators.moving_averages.sma_20.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>SMA 50</span>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>${analysis.indicators.moving_averages.sma_50.toFixed(2)}</span>
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
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>${analysis.indicators.bollinger.upper.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Middle</span>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>${analysis.indicators.bollinger.middle.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={isDark ? 'text-slate-400' : 'text-slate-600'}>Lower</span>
                      <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>${analysis.indicators.bollinger.lower.toFixed(2)}</span>
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
    </div>
  )
}
