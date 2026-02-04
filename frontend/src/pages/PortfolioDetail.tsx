import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { portfolioApi, stocksApi } from '../lib/api'
import { Portfolio, Position, Transaction } from '../types'
import { toast } from 'sonner'
import { ArrowLeft, TrendingUp, TrendingDown, DollarSign, Pencil, Trash2, Plus, X, Search } from 'lucide-react'
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
  const [data, setData] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  const [showEditModal, setShowEditModal] = useState(false)
  const [editingPosition, setEditingPosition] = useState<Position | null>(null)
  const [editQuantity, setEditQuantity] = useState('')
  const [editAvgCost, setEditAvgCost] = useState('')
  const [saving, setSaving] = useState(false)

  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletingPosition, setDeletingPosition] = useState<Position | null>(null)

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
    }
  }, [id])

  const loadPortfolio = async () => {
    try {
      const response = await portfolioApi.detail(Number(id))
      setData(response.data)
      
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

  const loadCurrentPrices = async (symbols: string[]) => {
    const prices: Record<string, number> = {}
    for (const symbol of symbols) {
      try {
        const response = await stocksApi.info(symbol)
        prices[symbol] = response.data.current_price
      } catch {
        prices[symbol] = 0
      }
    }
    setCurrentPrices(prices)
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
        <Link to="/portfolios" className="text-sky-400 hover:text-sky-300 mt-2 inline-block">
          Back to portfolios
        </Link>
      </div>
    )
  }

  const { portfolio, positions, transactions } = data

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

  const totalReturn = totalValue - Number(portfolio.initial_investment)
  const totalReturnPct = (totalReturn / Number(portfolio.initial_investment)) * 100

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
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/portfolios" className={`p-2 ${isDark ? 'hover:bg-slate-800/50' : 'hover:bg-slate-100'} rounded-lg transition-colors border border-transparent ${isDark ? 'hover:border-slate-700/50' : 'hover:border-slate-200'}`}>
            <ArrowLeft className={`w-5 h-5 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
          </Link>
          <div>
            <h1 className={`text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{portfolio.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded-full border backdrop-blur-sm ${
                portfolio.mode === 'auto' 
                  ? 'bg-purple-500/20 text-purple-300 border-purple-500/30' 
                  : 'bg-sky-500/20 text-sky-300 border-sky-500/30'
              }`}>
                {portfolio.mode === 'auto' ? 'Auto' : 'Manual'}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full border backdrop-blur-sm ${
                portfolio.risk_tolerance === 'conservative'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                  : portfolio.risk_tolerance === 'aggressive'
                  ? 'bg-red-500/20 text-red-300 border-red-500/30'
                  : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
              }`}>
                {portfolio.risk_tolerance}
              </span>
              <span className="text-sm text-slate-500">
                Created {format(new Date(portfolio.created_at), 'MMM d, yyyy')}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-5 h-5" />
          Add Stock
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Initial Investment</p>
          <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            ${Number(portfolio.initial_investment).toLocaleString()}
          </p>
        </div>
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Current Value</p>
          <p className={`text-2xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
            ${totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Total Return</p>
          <p className={`text-2xl font-bold flex items-center gap-1 ${
            totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'
          }`} style={{ textShadow: totalReturn >= 0 ? '0 0 15px rgba(52, 211, 153, 0.4)' : '0 0 15px rgba(248, 113, 113, 0.4)' }}>
            {totalReturn >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
            {totalReturn >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
          </p>
        </div>
        <div className="card">
          <p className={`text-sm ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>Expected Sharpe</p>
          <p className="text-2xl font-bold text-sky-400">
            {Number(portfolio.expected_sharpe || 0).toFixed(2)}
          </p>
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
                  const currentPrice = currentPrices[position.symbol] || Number(position.avg_cost)
                  const marketValue = currentPrice * Number(position.quantity)
                  const costBasis = Number(position.avg_cost) * Number(position.quantity)
                  const pl = marketValue - costBasis
                  const plPct = costBasis > 0 ? (pl / costBasis) * 100 : 0

                  return (
                    <tr key={position.id} className={`border-b ${isDark ? 'border-slate-700/50' : 'border-slate-200'} last:border-b-0 ${isDark ? 'bg-slate-800/30 hover:bg-slate-700/30' : 'bg-slate-50 hover:bg-slate-100'} transition-colors`}>
                      <td className={`py-3 font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>{position.symbol.replace('.AX', '')}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{Number(position.quantity).toFixed(2)}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>${Number(position.avg_cost).toFixed(2)}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>${currentPrice.toFixed(2)}</td>
                      <td className={`py-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>${marketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td className={`py-3 font-medium ${pl >= 0 ? 'text-emerald-400' : 'text-red-400'}`} style={{ textShadow: pl >= 0 ? '0 0 10px rgba(52, 211, 153, 0.3)' : '0 0 10px rgba(248, 113, 113, 0.3)' }}>
                        {pl >= 0 ? '+' : ''}{plPct.toFixed(1)}%
                      </td>
                      <td className="py-3 text-right">
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
                  <div className="p-3 bg-sky-500/20 rounded-lg border border-sky-500/30">
                    <p className="font-medium text-sky-300">{selectedStock.symbol.replace('.AX', '')}</p>
                    <p className="text-sm text-sky-400">{selectedStock.name}</p>
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
    </div>
  )
}
