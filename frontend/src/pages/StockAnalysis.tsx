import { useState } from 'react'
import { indicatorsApi } from '../lib/api'
import { TechnicalAnalysis } from '../types'
import { toast } from 'sonner'
import { Search, TrendingUp, TrendingDown, Activity, AlertCircle } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

export default function StockAnalysis() {
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
    if (signal === 'buy') return 'text-emerald-600 bg-emerald-100'
    if (signal === 'sell') return 'text-red-600 bg-red-100'
    return 'text-slate-600 bg-slate-100'
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Stock Analysis</h1>
        <p className="text-slate-600 mt-1">
          Technical indicator analysis with RSI, MACD, and Bollinger Bands
        </p>
      </div>

      <div className="card">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && analyzeStock()}
              placeholder="Enter ASX stock symbol (e.g., BHP, CBA, CSL)"
              className="input pl-10"
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
            <div className="card">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Price Chart</h2>
              {chartData && (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData}>
                    <XAxis 
                      dataKey="date" 
                      tick={{ fontSize: 12 }}
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-AU', { month: 'short' })}
                    />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 12 }} />
                    <Tooltip 
                      labelFormatter={(value) => new Date(value).toLocaleDateString()}
                      formatter={(value: number) => [`$${value?.toFixed(2) || 'N/A'}`, '']}
                    />
                    <Line type="monotone" dataKey="price" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="sma20" stroke="#8b5cf6" strokeWidth={1} dot={false} opacity={0.7} />
                    <Line type="monotone" dataKey="sma50" stroke="#f59e0b" strokeWidth={1} dot={false} opacity={0.7} />
                    <Line type="monotone" dataKey="bbUpper" stroke="#94a3b8" strokeWidth={1} dot={false} strokeDasharray="5 5" />
                    <Line type="monotone" dataKey="bbLower" stroke="#94a3b8" strokeWidth={1} dot={false} strokeDasharray="5 5" />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <div className="flex gap-4 mt-4 text-sm">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-sky-500"></span> Price
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-purple-500"></span> SMA 20
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-amber-500"></span> SMA 50
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-0.5 bg-slate-400" style={{ borderTop: '1px dashed' }}></span> Bollinger
                </span>
              </div>
            </div>

            <div className="card">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">RSI (Relative Strength Index)</h2>
              {chartData && (
                <ResponsiveContainer width="100%" height={150}>
                  <LineChart data={chartData}>
                    <XAxis 
                      dataKey="date" 
                      tick={{ fontSize: 12 }}
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-AU', { month: 'short' })}
                    />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                    <Tooltip 
                      labelFormatter={(value) => new Date(value).toLocaleDateString()}
                      formatter={(value: number) => [value?.toFixed(2) || 'N/A', 'RSI']}
                    />
                    <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" />
                    <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" />
                    <Line type="monotone" dataKey="rsi" stroke="#6366f1" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <div className="flex gap-4 mt-2 text-sm text-slate-500">
                <span>Above 70: Overbought (Sell signal)</span>
                <span>Below 30: Oversold (Buy signal)</span>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-slate-900">
                  {analysis.symbol.replace('.AX', '')}
                </h2>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  analysis.trend === 'uptrend' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
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
              
              <p className="text-3xl font-bold text-slate-900 mb-4">
                ${analysis.current_price.toFixed(2)}
              </p>

              <div className={`p-4 rounded-lg ${getSignalColor(analysis.overall_signal)}`}>
                <p className="font-semibold capitalize">
                  Overall Signal: {analysis.overall_signal.toUpperCase()}
                </p>
              </div>
            </div>

            <div className="card">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Indicators</h2>
              
              <div className="space-y-4">
                <div className="p-3 bg-slate-50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium">RSI</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      getSignalColor(analysis.indicators.rsi.signal.signal)
                    }`}>
                      {analysis.indicators.rsi.signal.signal.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-2xl font-bold">{analysis.indicators.rsi.value.toFixed(1)}</p>
                  <p className="text-sm text-slate-500 mt-1">
                    {analysis.indicators.rsi.signal.explanation}
                  </p>
                </div>

                <div className="p-3 bg-slate-50 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium">MACD</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      getSignalColor(analysis.indicators.macd.signal.signal)
                    }`}>
                      {analysis.indicators.macd.signal.signal.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600">
                    MACD: {analysis.indicators.macd.macd_line.toFixed(4)}
                  </p>
                  <p className="text-sm text-slate-600">
                    Signal: {analysis.indicators.macd.signal_line.toFixed(4)}
                  </p>
                  <p className="text-sm text-slate-500 mt-1">
                    {analysis.indicators.macd.signal.explanation}
                  </p>
                </div>

                <div className="p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium">Moving Averages</span>
                  <div className="mt-2 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">SMA 20</span>
                      <span className="font-medium">${analysis.indicators.moving_averages.sma_20.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">SMA 50</span>
                      <span className="font-medium">${analysis.indicators.moving_averages.sma_50.toFixed(2)}</span>
                    </div>
                    <p className="text-slate-500 mt-1">
                      Price is {analysis.indicators.moving_averages.price_vs_sma50} SMA 50
                    </p>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium">Bollinger Bands</span>
                  <div className="mt-2 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Upper</span>
                      <span className="font-medium">${analysis.indicators.bollinger.upper.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Middle</span>
                      <span className="font-medium">${analysis.indicators.bollinger.middle.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Lower</span>
                      <span className="font-medium">${analysis.indicators.bollinger.lower.toFixed(2)}</span>
                    </div>
                    <p className="text-slate-500 mt-1">
                      Position: {analysis.indicators.bollinger.position.replace('_', ' ')}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5" />
              <div>
                <p className="text-sm text-amber-800 font-medium">Disclaimer</p>
                <p className="text-sm text-amber-700 mt-1">
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
