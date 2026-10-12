import { Outlet, NavLink } from 'react-router-dom'
import logo from '../assets/logo.png'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/profile'
import {
  LayoutDashboard,
  Wrench,
  Wand2,
  Activity,
  Briefcase,
  LineChart,
  Menu,
  X,
  Settings,
  Moon,
  Sun,
  BookOpen,
  Inbox,
  ShieldCheck,
  ClipboardList,
  SlidersHorizontal,
  OctagonX,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import HelpModal from './HelpModal'
import TwsStatusPill from './TwsStatusPill'
import { aiApi, apiErrorMessage } from '../lib/api'

type Item = { path: string; label: string; icon: LucideIcon; badge?: boolean }

const groups: { title: string; items: Item[] }[] = [
  { title: 'Overview', items: [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/portfolios', label: 'Portfolios', icon: Briefcase },
  ] },
  { title: 'Build', items: [
    { path: '/auto-builder', label: 'Auto Builder', icon: Wand2 },
    { path: '/manual-builder', label: 'Manual Builder', icon: Wrench },
    { path: '/capm-builder', label: 'CAPM Builder', icon: Activity },
  ] },
  { title: 'Research', items: [
    { path: '/analysis', label: 'Stock Analysis', icon: LineChart },
  ] },
  { title: 'Trading', items: [
    { path: '/ai-inbox', label: 'AI Inbox', icon: Inbox, badge: true },
    { path: '/paper-orders', label: 'Orders', icon: ClipboardList },
    { path: '/brokerage', label: 'Brokerage', icon: ShieldCheck },
    { path: '/ai-trading', label: 'AI Settings', icon: SlidersHorizontal },
  ] },
]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
    isActive ? 'nav-active font-medium' : 'theme-text-secondary nav-hover'
  }`

/** How many AI proposals are waiting for an answer (sidebar badge). */
function usePendingCount() {
  const [count, setCount] = useState(0)
  useEffect(() => {
    let alive = true
    const refresh = () => aiApi.listSignals('pending')
      .then((res) => { if (alive) setCount(Array.isArray(res.data) ? res.data.length : 0) })
      .catch(() => undefined)
    refresh()
    const timer = window.setInterval(refresh, 30000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])
  return count
}

function Nav({ pending, onNavigate, onGlossary }: { pending: number; onNavigate?: () => void; onGlossary: () => void }) {
  return (
    <nav className="space-y-5">
      {groups.map((g) => (
        <div key={g.title} className="space-y-0.5">
          <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider theme-text-muted">{g.title}</p>
          {g.items.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === '/'} onClick={onNavigate} className={linkClass}>
              <item.icon className="w-4 h-4" />
              <span className="flex-1">{item.label}</span>
              {item.badge && pending > 0 && (
                <span className="num text-[11px] font-semibold px-1.5 rounded-full" style={{ background: 'var(--ink)', color: 'var(--on-ink)' }}
                  data-testid="inbox-badge">{pending}</span>
              )}
            </NavLink>
          ))}
        </div>
      ))}
      <div className="space-y-0.5">
        <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider theme-text-muted">Help</p>
        <button type="button" onClick={() => { onGlossary(); onNavigate?.() }}
          className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm theme-text-secondary nav-hover" data-testid="glossary-button">
          <BookOpen className="w-4 h-4" />
          Help & Glossary
        </button>
        <NavLink to="/settings" onClick={onNavigate} className={linkClass}>
          <Settings className="w-4 h-4" />
          Settings
        </NavLink>
      </div>
    </nav>
  )
}

/** Sidebar card: TWS connections plus the Emergency stop (same as the tray's). */
function StatusCard() {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const stop = async () => {
    setBusy(true)
    try {
      const res = await aiApi.killSwitch()
      const working = Number((res.data as { paper_orders_cancel_requested?: number })?.paper_orders_cancel_requested ?? 0)
      toast.success(working
        ? `Stopped. Cancel requested for ${working} working order(s); TWS confirms each one on the Orders page.`
        : 'Stopped. AI Trading, paper and real-money trading are off. Sapient had no working orders at IBKR.')
      setConfirm(false)
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Emergency stop failed'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="rounded-xl border theme-border p-2 space-y-1" style={{ background: 'var(--bg-card)' }}>
      <TwsStatusPill />
      <TwsStatusPill profile="live" />
      {!confirm ? (
        <button type="button" onClick={() => setConfirm(true)} data-testid="sidebar-emergency-stop"
          className="flex items-center justify-center gap-2 w-full rounded-lg px-3 py-2 text-xs font-semibold text-neg border"
          style={{ borderColor: 'var(--neg)' }}>
          <OctagonX className="w-4 h-4" /> Emergency stop
        </button>
      ) : (
        <div className="space-y-2 p-1">
          <p className="text-xs theme-text-secondary">Turn off all automatic trading and ask TWS to cancel Sapient's working orders?</p>
          <div className="flex gap-2">
            <button type="button" className="btn-danger !py-1.5 !px-3 text-xs flex-1" onClick={stop} disabled={busy}>
              {busy ? 'Stopping…' : 'Stop everything'}
            </button>
            <button type="button" className="btn-secondary !py-1.5 !px-3 text-xs" onClick={() => setConfirm(false)} disabled={busy}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { theme, toggleTheme } = useTheme()
  const { profile } = useProfile()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const pending = usePendingCount()
  const isDark = theme === 'dark'
  const ThemeIcon = isDark ? Sun : Moon

  return (
    <div className="min-h-screen flex">
      <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:sticky lg:top-0 lg:h-screen border-r theme-border"
        style={{ background: 'var(--bg-side)' }}>
        <div className="px-4 pt-4 pb-3 flex items-center gap-2">
          <img src={logo} alt="" className="w-9 h-9 rounded-lg" />
          <div>
            <h1 className="text-lg font-semibold theme-text leading-none">Sapient</h1>
            <p className="text-[11px] theme-text-muted mt-1">Smart Portfolios, Smarter Returns</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <Nav pending={pending} onGlossary={() => setShowHelp(true)} />
        </div>
        <div className="p-3 space-y-2 border-t theme-border">
          <StatusCard />
          <div className="flex items-center gap-2 px-1">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
              style={{ background: 'var(--ink)', color: 'var(--on-ink)' }}>
              {(profile?.display_name || 'S').slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium theme-text truncate">{profile?.display_name || 'Local profile'}</p>
              <p className="text-[11px] theme-text-muted">Data stays on this PC</p>
            </div>
            <button type="button" onClick={toggleTheme} className="p-2 rounded-lg theme-text-secondary nav-hover"
              title={isDark ? 'Light mode' : 'Dark mode'} aria-label={isDark ? 'Light mode' : 'Dark mode'}>
              <ThemeIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="lg:hidden border-b theme-border px-4 py-2 flex items-center justify-between" style={{ background: 'var(--bg-side)' }}>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="p-2 -ml-2 theme-text-secondary"
              aria-label="Menu">
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            <img src={logo} alt="" className="w-8 h-8 rounded-lg" />
            <h1 className="text-lg font-semibold theme-text">Sapient</h1>
          </div>
          <button type="button" onClick={toggleTheme} className="p-2 rounded-lg theme-text-secondary" aria-label="Switch theme">
            <ThemeIcon className="w-5 h-5" />
          </button>
        </header>

        {mobileMenuOpen && (
          <div className="lg:hidden border-b theme-border px-3 py-3 space-y-3" style={{ background: 'var(--bg-side)' }}>
            <Nav pending={pending} onNavigate={() => setMobileMenuOpen(false)} onGlossary={() => setShowHelp(true)} />
            <StatusCard />
          </div>
        )}

        <main className="flex-1 p-3 sm:p-6 overflow-x-hidden overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
    </div>
  )
}
