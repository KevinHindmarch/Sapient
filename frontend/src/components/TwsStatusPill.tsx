import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { twsApi } from '../lib/api'

export const TWS_STATE_LABELS: Record<string, { text: string; tone: 'green' | 'amber' | 'red' }> = {
  NOT_CONFIGURED: { text: 'Not set up', tone: 'amber' },
  SDK_MISSING: { text: 'IBKR API software missing', tone: 'red' },
  OFFLINE: { text: 'TWS not running', tone: 'amber' },
  CLIENT_ID_IN_USE: { text: 'Client ID in use', tone: 'red' },
  ACCOUNT_MISMATCH: { text: 'Different account', tone: 'red' },
  IBKR_DISCONNECTED: { text: 'TWS lost IBKR', tone: 'red' },
  SYNCHRONIZING: { text: 'Connecting…', tone: 'amber' },
  READY: { text: 'Connected', tone: 'green' },
  ERROR: { text: 'Problem', tone: 'red' },
}

const DOT = { green: 'bg-emerald-500', amber: 'bg-amber-500', red: 'bg-red-500' }

// Small always-visible TWS connection indicator for the sidebar.
export default function TwsStatusPill() {
  const [state, setState] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const refresh = () => twsApi.status().then((res) => { if (alive) setState(res.data.state) }).catch(() => undefined)
    refresh()
    const timer = window.setInterval(refresh, 10000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])

  const label = TWS_STATE_LABELS[state ?? 'NOT_CONFIGURED'] ?? { text: state ?? '', tone: 'amber' as const }
  return (
    <NavLink to="/brokerage" className="flex items-center gap-2 px-4 py-2 text-xs theme-text-secondary hover:underline" data-testid="tws-pill">
      <span className={`w-2.5 h-2.5 rounded-full ${DOT[label.tone]}`} />
      TWS: {label.text}
    </NavLink>
  )
}
