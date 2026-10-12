import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ValuePoint } from '../lib/api'

export type Period = '1M' | '3M' | '1Y' | 'All'
export const PERIODS: Period[] = ['1M', '3M', '1Y', 'All']
const DAYS: Record<Period, number> = { '1M': 31, '3M': 92, '1Y': 366, All: 100000 }

export interface Series {
  key: string
  label: string
  color: string
  points: ValuePoint[]
  /** Dashed line drawn over the filled area (e.g. the original forecast). */
  dashed?: boolean
  /** Step line for money put in. */
  flat?: boolean
}

const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

/** Value over time with optional extra lines. The first series is filled; the rest are lines. */
export default function ValueChart({ series, period, prefix, height = 260, until }: {
  series: Series[]; period: Period; prefix: string; height?: number
  /** Last date to draw (lets a forecast run past today). Defaults to the last point of any series. */
  until?: string
}) {
  const data = useMemo(() => {
    const today = new Date()
    const from = new Date(today.getTime() - DAYS[period] * 86400000).toISOString().slice(0, 10)
    const dates = new Set<string>()
    for (const s of series) for (const p of s.points) if (p.date >= from && (!until || p.date <= until)) dates.add(p.date)
    const sorted = [...dates].sort()
    // Lines are drawn only between their own points (connectNulls); values are not carried past the end.
    const lookups = series.map((s) => new Map(s.points.map((p) => [p.date, p.value])))
    return sorted.map((d) => {
      const row: Record<string, number | string | null> = { date: d }
      series.forEach((s, i) => { row[s.key] = lookups[i].get(d) ?? null })
      return row
    })
  }, [series, period, until])

  if (!data.length) {
    return <div className="flex items-center justify-center text-sm theme-text-muted" style={{ height }}>No history yet</div>
  }
  const [main, ...rest] = series
  const fmt = (v: number) => `${prefix}${Math.round(v).toLocaleString()}`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`fill-${main.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={main.color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={main.color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border-color)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false}
          tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={fmt} tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false} tickLine={false} width={78} domain={['auto', 'auto']} />
        <Tooltip
          contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 12, fontSize: 12 }}
          labelStyle={{ color: 'var(--text-secondary)' }}
          labelFormatter={(d) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
          formatter={(v, name) => [typeof v === 'number' ? `${prefix}${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—',
            series.find((s) => s.key === name)?.label ?? String(name)]}
        />
        <Area type="monotone" dataKey={main.key} stroke={main.color} strokeWidth={2} fill={`url(#fill-${main.key})`}
          connectNulls dot={false} isAnimationActive={false} />
        {rest.map((s) => (
          <Line key={s.key} type={s.flat ? 'stepAfter' : 'monotone'} dataKey={s.key} stroke={s.color} strokeWidth={s.dashed ? 1.75 : 2}
            strokeDasharray={s.dashed ? '6 5' : undefined} dot={false} connectNulls isAnimationActive={false} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Tiny line for portfolio rows. */
export function Sparkline({ points, color, width = 96, height = 28 }: { points: ValuePoint[]; color: string; width?: number; height?: number }) {
  if (points.length < 2) return <svg width={width} height={height} aria-hidden="true" />
  const vals = points.map((p) => p.value)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const span = hi - lo || 1
  const d = vals.map((v, i) => `${i ? 'L' : 'M'}${((i / (vals.length - 1)) * width).toFixed(1)},${(height - 2 - ((v - lo) / span) * (height - 4)).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
