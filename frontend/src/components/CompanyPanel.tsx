import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { apiErrorMessage, stocksApi } from '../lib/api'
import type { StockInfo } from '../types'

/**
 * "What does this company do?": click any company (a holding, a builder's pick, an AI proposal)
 * to open a side panel with Yahoo's description and key facts. Research data, not advice.
 */
type Open = (symbol: string) => void
const CompanyContext = createContext<Open>(() => undefined)

export function useCompany(): Open {
  return useContext(CompanyContext)
}

/** A company name or symbol that opens the panel. */
export function CompanyLink({ symbol, children, className = '' }: { symbol: string; children?: ReactNode; className?: string }) {
  const open = useCompany()
  return (
    <button type="button" className={`company-link text-left ${className}`} onClick={(e) => { e.stopPropagation(); open(symbol) }}
      title="What does this company do?" data-testid={`company-${symbol}`}>
      {children ?? symbol.replace('.AX', '')}
    </button>
  )
}

const short = (n: number) => n >= 1e12 ? `${(n / 1e12).toFixed(2)} trillion` : n >= 1e9 ? `${(n / 1e9).toFixed(1)} billion`
  : n >= 1e6 ? `${(n / 1e6).toFixed(0)} million` : n.toLocaleString()

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [symbol, setSymbol] = useState<string | null>(null)
  const [info, setInfo] = useState<StockInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const open = useCallback<Open>((s) => { setSymbol(s); setInfo(null); setError(null) }, [])
  const close = useCallback(() => setSymbol(null), [])

  useEffect(() => {
    if (!symbol) return
    let live = true
    stocksApi.info(symbol)
      .then((res) => { if (live) setInfo(res.data) })
      .catch((err) => { if (live) setError(apiErrorMessage(err, 'Could not load this company right now.')) })
    return () => { live = false }
  }, [symbol])

  useEffect(() => {
    if (!symbol) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [symbol, close])

  const asx = symbol?.endsWith('.AX')
  const sym = asx ? 'A$' : 'US$'
  const range = useMemo(() => {
    if (!info?.week52_low || !info?.week52_high || !info.current_price) return null
    const span = info.week52_high - info.week52_low
    return span > 0 ? Math.min(100, Math.max(0, ((info.current_price - info.week52_low) / span) * 100)) : null
  }, [info])

  return (
    <CompanyContext.Provider value={open}>
      {children}
      {symbol && (
        <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Company details">
          <button type="button" aria-label="Close" className="absolute inset-0 bg-black/40" onClick={close} />
          <aside className="relative h-full w-full max-w-[460px] overflow-y-auto border-l theme-border p-6 space-y-5 animate-fade-in"
            style={{ background: 'var(--bg-card)' }} data-testid="company-panel">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-2 min-w-0">
                <div className="flex flex-wrap gap-1.5">
                  <span className={`chip ${asx ? 'chip-aud' : 'chip-usd'}`}>{asx ? 'ASX · A$' : 'US · US$'}</span>
                  <span className="chip num">{symbol.replace('.AX', '')}</span>
                </div>
                <h2 className="text-xl font-semibold theme-text leading-tight">{info?.name ?? symbol}</h2>
                {info && <p className="text-sm theme-text-secondary">{[info.sector, info.industry].filter((x) => x && x !== 'Unknown').join(' · ')}</p>}
              </div>
              <button type="button" onClick={close} aria-label="Close" className="btn-secondary !p-2 !rounded-lg"><X className="w-4 h-4" /></button>
            </div>

            {!info && !error && <div className="h-40 rounded-xl loading-shimmer" />}
            {error && <p className="text-sm text-neg">{error}</p>}

            {info && (
              <>
                {info.current_price > 0 && (
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-xs theme-text-muted">Last price</p>
                      <p className="num text-3xl font-semibold theme-text">{sym}{info.current_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</p>
                    </div>
                    {info.pe_ratio && <div className="text-right"><p className="text-xs theme-text-muted">Price / earnings</p><p className="num text-lg theme-text">{info.pe_ratio.toFixed(1)}</p></div>}
                  </div>
                )}
                {range !== null && (
                  <div className="space-y-1.5">
                    <p className="text-xs theme-text-muted">Price over the last 12 months</p>
                    <div className="relative h-2 rounded-full" style={{ background: 'var(--chip)' }}>
                      <span className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2"
                        style={{ left: `calc(${range}% - 6px)`, background: asx ? 'var(--aud)' : 'var(--usd)', borderColor: 'var(--bg-card)' }} />
                    </div>
                    <div className="flex justify-between num text-xs theme-text-muted">
                      <span>low {sym}{info.week52_low?.toFixed(2)}</span><span>high {sym}{info.week52_high?.toFixed(2)}</span>
                    </div>
                  </div>
                )}
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold theme-text">What the company does</h3>
                  <p className="text-sm leading-relaxed theme-text-secondary whitespace-pre-line">
                    {info.description || 'Yahoo has no description for this company.'}
                  </p>
                </section>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  {[
                    ['Company size', info.market_cap ? `${sym}${short(info.market_cap)}` : null],
                    ['Employees', info.employees ? info.employees.toLocaleString() : null],
                    ['Based in', info.country || null],
                    ['Listed on', info.exchange || null],
                  ].filter(([, v]) => v).map(([k, v]) => (
                    <div key={k} className="rounded-xl p-3 surface-2">
                      <dt className="text-xs theme-text-muted">{k}</dt>
                      <dd className="font-medium theme-text">{v}</dd>
                    </div>
                  ))}
                </dl>
                {info.website && <p className="text-xs theme-text-muted">Website: {info.website.replace(/^https?:\/\//, '')}</p>}
                <p className="text-xs theme-text-muted">From Yahoo Finance. Research information, not a recommendation.</p>
              </>
            )}
          </aside>
        </div>
      )}
    </CompanyContext.Provider>
  )
}
