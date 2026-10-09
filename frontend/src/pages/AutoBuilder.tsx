import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { portfolioApi, normaliseWeights } from '../lib/api'
import { toast } from 'sonner'
import { Wand2, Save, TrendingUp, Loader2, CheckCircle, Info, AlertTriangle, Target, Globe, SlidersHorizontal } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import { useTheme } from '../lib/theme'
import WeightEditor from '../components/WeightEditor'

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6']

type Market = 'ASX' | 'US'

interface StockFundamentals {
  symbol: string
  name: string
  sector: string
  current_price: number
  market_cap: number
  earnings_yield: number | null
  roe: number | null
  earnings_growth: number | null
  dividend_yield: number | null
  value_score: number
  quality_score: number
  growth_score: number
  size_score?: number
  momentum_score?: number
  composite_score: number
  expected_return: number
}

interface OptimizationResult {
  weights: Record<string, number>
  expected_return: number
  volatility: number
  sharpe_ratio: number
  var_95: number
  max_drawdown: number
  portfolio_dividend_yield: number
  correlation_matrix?: number[][]
  correlation_symbols?: string[]
  stock_fundamentals?: {
    symbol: string
    name: string
    weight: number
    expected_return: number
    value_score: number
    quality_score: number
    composite_score: number
  }[]
}

const formSchema = z.object({
  investment_amount: z.number().min(1000, 'Minimum $1,000').max(10000000, 'Maximum $10,000,000'),
  portfolio_size: z.enum(['small', 'medium', 'large']),
  risk_tolerance: z.enum(['conservative', 'moderate', 'aggressive']),
})

type FormData = z.infer<typeof formSchema>

const PORTFOLIO_SIZES = {
  small: { target: 6, label: 'Small (5-8 stocks)' },
  medium: { target: 10, label: 'Medium (8-12 stocks)' },
  large: { target: 15, label: 'Large (12-20 stocks)' },
}

const getCorrelationColor = (value: number): string => {
  if (value >= 0.7) return 'bg-red-500/80 text-white'
  if (value >= 0.4) return 'bg-amber-500/80 text-white'
  if (value >= 0) return 'bg-emerald-500/80 text-white'
  if (value >= -0.4) return 'bg-sky-500/80 text-white'
  return 'bg-blue-600/80 text-white'
}

const CorrelationMatrix = ({ matrix, symbols, isDark }: { matrix: number[][], symbols: string[], isDark: boolean }) => {
  const avgCorr = matrix.reduce((sum, row, i) => 
    sum + row.reduce((rowSum, val, j) => i !== j ? rowSum + val : rowSum, 0), 0
  ) / (matrix.length * (matrix.length - 1))
  
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="p-2"></th>
              {symbols.map(s => (
                <th key={s} className={`p-2 font-semibold text-center ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{s.replace('.AX', '')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={symbols[i]}>
                <td className={`p-2 font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{symbols[i].replace('.AX', '')}</td>
                {row.map((val, j) => (
                  <td key={j} className={`p-2 text-center rounded transition-all duration-300 ${i === j ? (isDark ? 'bg-slate-700' : 'bg-slate-200') : getCorrelationColor(val)}`}>
                    {val.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className={`flex items-center gap-2 p-3 rounded-lg border backdrop-blur-sm ${
        avgCorr < 0.3
          ? isDark ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-emerald-100 text-emerald-700 border-emerald-300'
          : avgCorr < 0.5
          ? isDark ? 'bg-sky-500/20 text-sky-300 border-sky-500/30' : 'bg-sky-100 text-sky-700 border-sky-300'
          : isDark ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' : 'bg-amber-100 text-amber-700 border-amber-300'
      }`}>
        {avgCorr < 0.3 ? <CheckCircle className="w-5 h-5" /> :
         avgCorr < 0.5 ? <Info className="w-5 h-5" /> :
         <AlertTriangle className="w-5 h-5" />}
        <span className="text-sm font-medium">
          Avg. correlation: {avgCorr.toFixed(2)} - {
            avgCorr < 0.3 ? 'Excellent diversification!' :
            avgCorr < 0.5 ? 'Good diversification' :
            'Consider adding less correlated assets'
          }
        </span>
      </div>
    </div>
  )
}

const getScoreColor = (score: number) => {
  if (score >= 70) return 'text-emerald-600 dark:text-emerald-400'
  if (score >= 50) return 'text-sky-600 dark:text-sky-400'
  if (score >= 30) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}

const formatMarketCap = (val: number) => {
  if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`
  if (val >= 1e6) return `$${(val / 1e6).toFixed(0)}M`
  return `$${val.toLocaleString()}`
}

export default function AutoBuilder() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  
  const [market, setMarket] = useState<Market>('ASX')
  const [building, setBuilding] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [scannedStocks, setScannedStocks] = useState<StockFundamentals[]>([])
  const [selectedStocks, setSelectedStocks] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [progress, setProgress] = useState('')
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [portfolioName, setPortfolioName] = useState('')
  const [editedWeights, setEditedWeights] = useState<Record<string, number> | null>(null)
  const [showWeightEditor, setShowWeightEditor] = useState(false)

  const { register, handleSubmit, formState: { errors }, watch } = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      investment_amount: 50000,
      portfolio_size: 'medium',
      risk_tolerance: 'moderate',
    },
  })

  const investmentAmount = watch('investment_amount')
  const riskTolerance = watch('risk_tolerance')
  
  const currency = market === 'US' ? 'USD' : 'AUD'
  const currencySymbol = market === 'US' ? '$' : 'A$'
  const marketLabel = market === 'US' ? 'S&P 500' : 'ASX200'

  const handleMarketChange = (newMarket: Market) => {
    setMarket(newMarket)
    setResult(null)
    setScannedStocks([])
    setSelectedStocks([])
  }

  const onSubmit = async (data: FormData) => {
    setBuilding(true)
    setProgress(`Scanning ${marketLabel} using Fama-French factors...`)
    setResult(null)
    setScannedStocks([])
    setSelectedStocks([])
    
    try {
      const sizeConfig = PORTFOLIO_SIZES[data.portfolio_size]
      const targetSize = sizeConfig.target
      
      const scanResponse = await portfolioApi.scanFundamentals(30, market)
      const stocks = scanResponse.data.stocks as StockFundamentals[]
      
      if (!stocks || stocks.length === 0) {
        throw new Error('No stock data available')
      }
      
      setProgress(`Found ${stocks.length} opportunities - selecting top ${targetSize}...`)
      setScannedStocks(stocks)
      
      const topStocks = stocks.slice(0, targetSize).map(s => s.symbol)
      
      if (topStocks.length < 2) {
        throw new Error('Not enough stocks with valid fundamentals')
      }
      
      setSelectedStocks(topStocks)
      setProgress(`Optimizing portfolio using fundamentals-weighted returns...`)
      
      const response = await portfolioApi.optimizeFundamentals(
        topStocks,
        data.investment_amount,
        data.risk_tolerance,
        '1y',
        market
      )
      
      setResult(response.data)
      setEditedWeights(null)
      setShowWeightEditor(false)
      toast.success(`Auto-built portfolio from ${scanResponse.data.total_scanned} ${marketLabel} stocks!`)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to build portfolio')
    } finally {
      setBuilding(false)
      setProgress('')
    }
  }

  const openSaveModal = () => {
    setPortfolioName('')
    setShowSaveModal(true)
  }

  const savePortfolio = async () => {
    if (!result || !portfolioName.trim()) return

    setSaving(true)
    try {
      const resultToSave = editedWeights ? { ...result, weights: normaliseWeights(editedWeights) } : result
      const saved = await portfolioApi.save(portfolioName.trim(), resultToSave, investmentAmount, 'auto', riskTolerance, market)
      if (saved.data.warning) toast.warning(`${saved.data.warning}. Those stocks were left out of the saved portfolio.`)
      toast.success('Portfolio saved. Buy it on paper or for real from its page.')
      if (saved.data?.portfolio_id) navigate(`/portfolios/${saved.data.portfolio_id}`)
      setShowSaveModal(false)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Failed to save portfolio')
    } finally {
      setSaving(false)
    }
  }

  const chartData = result ? Object.entries(result.weights)
    .sort(([, a], [, b]) => (b as number) - (a as number))
    .slice(0, 8)
    .map(([symbol, weight]) => ({
      name: symbol.replace('.AX', ''),
      value: (weight as number) * 100,
    })) : []

  const selectedStockDetails = scannedStocks.filter(s => selectedStocks.includes(s.symbol))

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Auto Portfolio Builder</h1>
          <p className={`mt-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
            Automatically generate an optimized portfolio using Fama-French fundamentals
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-slate-500" />
          <span className={`text-sm font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Market:</span>
          <div className={`inline-flex rounded-lg p-1 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
            <button
              onClick={() => handleMarketChange('ASX')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                market === 'ASX'
                  ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
                  : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              🇦🇺 ASX
            </button>
            <button
              onClick={() => handleMarketChange('US')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                market === 'US'
                  ? 'bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg'
                  : isDark ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              🇺🇸 S&P 500
            </button>
          </div>
        </div>
      </div>

      <div className={`card p-6 ${isDark ? 'bg-gradient-to-r from-indigo-500/20 to-purple-500/20 border-indigo-500/30' : 'bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-200'}`}>
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded-xl ${isDark ? 'bg-indigo-500/30' : 'bg-indigo-100'}`}>
            <Target className="w-8 h-8 text-indigo-400" />
          </div>
          <div>
            <h3 className={`font-semibold text-lg ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>How it works</h3>
            <p className={`mt-1 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Uses <strong>Fama-French multi-factor model</strong> backed by Nobel Prize-winning research:
            </p>
            <ul className={`mt-2 space-y-1 text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              <li><strong>Value</strong> = Earnings Yield, Price-to-Book (high = undervalued)</li>
              <li><strong>Quality</strong> = ROE, Profit Margins, Low Debt (profitability factor)</li>
              <li><strong>Size</strong> = Small-cap premium (smaller companies outperform)</li>
              <li><strong>Momentum</strong> = 12-month price trend (strongest 2024 factor)</li>
              <li><strong>Growth</strong> = Sustainable Growth Rate (ROE × Retention + Historical CAGR)</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <form onSubmit={handleSubmit(onSubmit)} className="card">
            <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Build Settings</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="label">Investment Amount ({currency})</label>
                <input
                  type="number"
                  {...register('investment_amount', { valueAsNumber: true })}
                  className="input"
                />
                {errors.investment_amount && (
                  <p className="error-text">{errors.investment_amount.message}</p>
                )}
              </div>

              <div>
                <label className="label">Portfolio Size</label>
                <select {...register('portfolio_size')} className="input">
                  {Object.entries(PORTFOLIO_SIZES).map(([key, config]) => (
                    <option key={key} value={key}>{config.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Risk Tolerance</label>
                <select {...register('risk_tolerance')} className="input">
                  <option value="conservative">Conservative</option>
                  <option value="moderate">Moderate</option>
                  <option value="aggressive">Aggressive</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={building}
              className="btn-primary mt-4 flex items-center gap-2"
            >
              {building ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Wand2 className="w-5 h-5" />
              )}
              {building ? progress || 'Building...' : `Build ${marketLabel} Portfolio`}
            </button>
          </form>

          {building && (
            <div className="card mt-6">
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-12 h-12 animate-spin text-indigo-400 mb-4" />
                <p className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{progress || 'Processing...'}</p>
                <p className={`mt-2 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Analyzing fundamentals and optimizing allocations</p>
                <p className={`mt-1 text-sm ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>This may take 30-60 seconds</p>
              </div>
            </div>
          )}

          {!building && result && selectedStockDetails.length > 0 && (
            <>
              <div className="card mt-6">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                  Selected Stocks ({selectedStockDetails.length})
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={isDark ? 'text-slate-400' : 'text-slate-600'}>
                        <th className="text-left p-2">Stock</th>
                        <th className="text-right p-2">Score</th>
                        <th className="text-right p-2">Weight</th>
                        <th className="text-right p-2">Amount</th>
                        <th className="text-right p-2">Value</th>
                        <th className="text-right p-2">Quality</th>
                        <th className="text-right p-2">Market Cap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.weights)
                        .sort(([, a], [, b]) => (b as number) - (a as number))
                        .map(([symbol, weight], index) => {
                          const stockInfo = scannedStocks.find(s => s.symbol === symbol)
                          const weightNum = weight as number
                          const amount = weightNum * investmentAmount
                          return (
                            <tr key={symbol} className={`border-t ${isDark ? 'border-slate-700/50 hover:bg-slate-800/50' : 'border-slate-200 hover:bg-slate-50'}`}>
                              <td className="p-2">
                                <div className="flex items-center gap-2">
                                  <div 
                                    className="w-3 h-3 rounded-full" 
                                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                                  />
                                  <div>
                                    <span className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{symbol.replace('.AX', '')}</span>
                                    <p className="text-xs text-slate-500 truncate max-w-[120px]">{stockInfo?.name || ''}</p>
                                  </div>
                                </div>
                              </td>
                              <td className={`p-2 text-right font-bold ${getScoreColor(stockInfo?.composite_score || 0)}`}>
                                {stockInfo?.composite_score?.toFixed(0) || '-'}
                              </td>
                              <td className="p-2 text-right">
                                <span className="font-medium text-sky-600 dark:text-sky-400">{(weightNum * 100).toFixed(1)}%</span>
                              </td>
                              <td className="p-2 text-right">
                                <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>{currencySymbol}{amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                              </td>
                              <td className={`p-2 text-right ${getScoreColor(stockInfo?.value_score || 0)}`}>
                                {stockInfo?.value_score?.toFixed(0) || '-'}
                              </td>
                              <td className={`p-2 text-right ${getScoreColor(stockInfo?.quality_score || 0)}`}>
                                {stockInfo?.quality_score?.toFixed(0) || '-'}
                              </td>
                              <td className={`p-2 text-right ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                                {stockInfo ? formatMarketCap(stockInfo.market_cap) : '-'}
                              </td>
                            </tr>
                          )
                        })}
                    </tbody>
                    <tfoot>
                      <tr className={`border-t-2 ${isDark ? 'border-slate-600/50' : 'border-slate-300'}`}>
                        <td className={`py-3 font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`} colSpan={2}>Total</td>
                        <td className="py-3 text-right font-semibold text-sky-600 dark:text-sky-400">100%</td>
                        <td className={`py-3 text-right font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{currencySymbol}{investmentAmount.toLocaleString()}</td>
                        <td colSpan={3}></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              <div className={`card mt-4 ${isDark ? 'bg-slate-800/50' : 'bg-slate-50'}`}>
                <h3 className={`font-semibold mb-3 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Score Legend</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-emerald-400"></div>
                    <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>70+ Excellent</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-sky-400"></div>
                    <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>50-69 Good</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-amber-400"></div>
                    <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>30-49 Average</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-400"></div>
                    <span className={isDark ? 'text-slate-300' : 'text-slate-700'}>Below 30 Poor</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="space-y-6">
          {result && (
            <>
              <div className="card">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Portfolio Metrics</h2>
                <div className="grid grid-cols-2 gap-3">
                  <div className={`border p-3 rounded-xl ${isDark ? 'bg-emerald-500/20 border-emerald-500/30' : 'bg-emerald-50 border-emerald-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>Expected Return</p>
                    <p className="text-xl font-bold text-emerald-500">
                      {(result.expected_return * 100).toFixed(2)}%
                    </p>
                  </div>
                  <div className={`border p-3 rounded-xl ${isDark ? 'bg-sky-500/20 border-sky-500/30' : 'bg-sky-50 border-sky-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-sky-300' : 'text-sky-700'}`}>Sharpe Ratio</p>
                    <p className="text-xl font-bold text-sky-700 dark:text-sky-400">{result.sharpe_ratio.toFixed(3)}</p>
                  </div>
                  <div className={`border p-3 rounded-xl ${isDark ? 'bg-amber-500/20 border-amber-500/30' : 'bg-amber-50 border-amber-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>Volatility</p>
                    <p className="text-xl font-bold text-amber-500">{(result.volatility * 100).toFixed(2)}%</p>
                  </div>
                  <div className={`border p-3 rounded-xl ${isDark ? 'bg-red-500/20 border-red-500/30' : 'bg-red-50 border-red-200'}`}>
                    <p className={`text-xs ${isDark ? 'text-red-300' : 'text-red-700'}`}>Max Drawdown</p>
                    <p className="text-xl font-bold text-red-500">{(result.max_drawdown * 100).toFixed(2)}%</p>
                  </div>
                </div>

                <div className={`mt-3 p-2 rounded-lg border ${isDark ? 'bg-purple-500/10 border-purple-500/30' : 'bg-purple-50 border-purple-200'}`}>
                  <p className={`text-xs ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>
                    Dividend Yield: {(result.portfolio_dividend_yield * 100).toFixed(2)}% • {Object.keys(result.weights).length} stocks
                  </p>
                </div>

                <div className="flex gap-2 mt-4">
                  <button
                    onClick={openSaveModal}
                    disabled={saving}
                    className="btn-success flex-1 flex items-center justify-center gap-2"
                  >
                    <Save className="w-5 h-5" />
                    Save Portfolio
                  </button>
                  <button
                    onClick={() => setShowWeightEditor(v => !v)}
                    className={`px-3 py-2 rounded-lg border text-sm font-medium flex items-center gap-1.5 transition-colors ${
                      showWeightEditor
                        ? isDark ? 'bg-sky-500/20 border-sky-500/30 text-sky-300' : 'bg-sky-100 border-sky-300 text-sky-700'
                        : isDark ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-slate-300 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <SlidersHorizontal className="w-4 h-4" />
                    Adjust
                  </button>
                </div>
              </div>

              {showWeightEditor && (
                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                    Customize Allocation
                  </h2>
                  <p className={`text-sm mb-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    Manually adjust weights below. The Save button will use your edited allocations.
                  </p>
                  <WeightEditor
                    weights={editedWeights ?? result!.weights}
                    investmentAmount={investmentAmount}
                    currency={currency}
                    onWeightsChange={setEditedWeights}
                  />
                </div>
              )}

              <div className="card">
                <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Top Holdings</h2>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={chartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      labelLine={{ stroke: isDark ? '#94a3b8' : '#64748b' }}
                    >
                      {chartData.map((_, index) => (
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      formatter={(value: number) => `${value.toFixed(2)}%`}
                      contentStyle={{ backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', border: isDark ? '1px solid rgba(148, 163, 184, 0.2)' : '1px solid rgba(148, 163, 184, 0.3)', borderRadius: '8px' }}
                      labelStyle={{ color: isDark ? '#f1f5f9' : '#0f172a' }}
                      itemStyle={{ color: isDark ? '#94a3b8' : '#64748b' }}
                    />
                    <Legend wrapperStyle={{ color: isDark ? '#94a3b8' : '#64748b' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {result.correlation_matrix && result.correlation_symbols && (
                <div className="card">
                  <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Correlation Matrix</h2>
                  <CorrelationMatrix 
                    matrix={result.correlation_matrix} 
                    symbols={result.correlation_symbols}
                    isDark={isDark}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {showSaveModal && result && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="rounded-2xl p-6 w-full max-w-md border transition-all duration-300" style={{ background: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.95)', borderColor: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(148, 163, 184, 0.3)', boxShadow: isDark ? '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 20px rgba(56, 189, 248, 0.1)' : '0 8px 32px rgba(0, 0, 0, 0.15)' }}>
            <h3 className={`text-xl font-bold mb-4 ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Save Portfolio</h3>
            <p className={`mb-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Enter a name for your {market === 'US' ? 'US' : 'Australian'} portfolio:</p>
            <input
              type="text"
              value={portfolioName}
              onChange={(e) => setPortfolioName(e.target.value)}
              placeholder={`e.g., ${market === 'US' ? 'US Growth' : 'ASX Value'} Portfolio`}
              className="input mb-4"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && portfolioName.trim() && savePortfolio()}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveModal(false)}
                className="btn-secondary flex-1"
                disabled={saving}
              >
                Cancel
              </button>
              <button
                onClick={savePortfolio}
                disabled={saving || !portfolioName.trim()}
                className="btn-success flex-1 flex items-center justify-center gap-2"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
