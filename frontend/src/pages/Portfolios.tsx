import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioApi } from '../lib/api'
import { Portfolio } from '../types'
import { Briefcase, ArrowRight, Calendar, TrendingUp, Shield, Trash2, X } from 'lucide-react'
import { format } from 'date-fns'
import { useTheme } from '../lib/theme'
import { toast } from 'sonner'

export default function Portfolios() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<Portfolio | null>(null)
  const [deleting, setDeleting] = useState(false)
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  useEffect(() => {
    loadPortfolios()
  }, [])

  const loadPortfolios = async () => {
    try {
      const response = await portfolioApi.list()
      setPortfolios(response.data)
    } catch (error) {
      console.error('Failed to load portfolios:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await portfolioApi.deletePortfolio(deleteTarget.id)
      toast.success(`"${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      loadPortfolios()
    } catch {
      toast.error('Failed to delete portfolio')
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sky-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className={`text-2xl sm:text-3xl font-bold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>My Portfolios</h1>
          <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-1 text-sm sm:text-base`}>Track and manage your optimized portfolios</p>
        </div>
        <Link to="/auto-builder" className="btn-primary flex items-center gap-2 shrink-0">
          <TrendingUp className="w-5 h-5" />
          New Portfolio
        </Link>
      </div>

      {portfolios.length === 0 ? (
        <div className="card text-center py-12">
          <Briefcase className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h2 className={`text-xl font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>No portfolios yet</h2>
          <p className={`${isDark ? 'text-slate-400' : 'text-slate-600'} mt-2 max-w-md mx-auto`}>
            Create your first portfolio using the Manual or Auto Portfolio Builder to start tracking your investments.
          </p>
          <div className="flex gap-4 justify-center mt-6">
            <Link to="/manual-builder" className="btn-secondary">
              Manual Builder
            </Link>
            <Link to="/auto-builder" className="btn-primary">
              Auto Builder
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {portfolios.map((portfolio) => (
            <div key={portfolio.id} className="relative group">
              <Link
                to={`/portfolios/${portfolio.id}`}
                className="card card-hover block"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1 min-w-0 pr-8">
                    <h3 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'} group-hover:text-sky-400 transition-colors`}>
                      {portfolio.name}
                    </h3>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
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
                    </div>
                  </div>
                  <ArrowRight className="w-5 h-5 text-slate-500 group-hover:text-sky-400 group-hover:translate-x-1 transition-all shrink-0" />
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-3 text-sm">
                    <div className={`p-2 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'} rounded border ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                      <Briefcase className={`w-4 h-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
                    </div>
                    <div>
                      <p className="text-slate-500">Investment</p>
                      <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                        ${Number(portfolio.initial_investment).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  {portfolio.expected_return && (
                    <div className="flex items-center gap-3 text-sm">
                      <div className="p-2 bg-emerald-500/20 rounded border border-emerald-500/30">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-slate-500">Expected Return</p>
                        <p className="font-medium text-emerald-400" style={{ textShadow: '0 0 10px rgba(52, 211, 153, 0.3)' }}>
                          +{(Number(portfolio.expected_return) * 100).toFixed(1)}%
                        </p>
                      </div>
                    </div>
                  )}

                  {portfolio.expected_sharpe && (
                    <div className="flex items-center gap-3 text-sm">
                      <div className="p-2 bg-sky-500/20 rounded border border-sky-500/30">
                        <Shield className="w-4 h-4 text-sky-400" />
                      </div>
                      <div>
                        <p className="text-slate-500">Sharpe Ratio</p>
                        <p className="font-medium text-sky-400">
                          {Number(portfolio.expected_sharpe).toFixed(2)}
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center gap-3 text-sm">
                    <div className={`p-2 ${isDark ? 'bg-slate-800/50' : 'bg-slate-100'} rounded border ${isDark ? 'border-slate-700/50' : 'border-slate-200'}`}>
                      <Calendar className={`w-4 h-4 ${isDark ? 'text-slate-400' : 'text-slate-600'}`} />
                    </div>
                    <div>
                      <p className="text-slate-500">Created</p>
                      <p className={`font-medium ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                        {format(new Date(portfolio.created_at), 'MMM d, yyyy')}
                      </p>
                    </div>
                  </div>
                </div>

                <div className={`mt-4 pt-4 border-t ${isDark ? 'border-slate-700/50' : 'border-slate-200'} text-sm text-slate-500 pr-8`}>
                  {portfolio.position_count} positions
                </div>
              </Link>

              {/* Delete button outside the Link to avoid triggering navigation */}
              <button
                onClick={() => setDeleteTarget(portfolio)}
                className="absolute bottom-3 right-3 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200 bg-red-500/10 hover:bg-red-500/20 text-red-400 hover:text-red-300 border border-red-500/20 hover:border-red-500/40"
                title="Delete portfolio"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className={`rounded-2xl border max-w-md w-full p-6 shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'
          }`}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-500/20 rounded-xl border border-red-500/30">
                  <Trash2 className="w-5 h-5 text-red-400" />
                </div>
                <h2 className={`text-lg font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>Delete Portfolio</h2>
              </div>
              <button onClick={() => setDeleteTarget(null)} className="text-slate-400 hover:text-slate-300">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className={`text-sm mb-2 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              Are you sure you want to delete <span className="font-semibold text-red-400">"{deleteTarget.name}"</span>?
            </p>
            <p className={`text-sm mb-6 ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
              This will permanently remove all positions, transactions and history. This action cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="btn-secondary flex-1"
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 px-4 py-2.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-xl border border-red-500/30 font-medium transition-all duration-200 disabled:opacity-50"
              >
                {deleting ? 'Deleting...' : 'Delete Portfolio'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
