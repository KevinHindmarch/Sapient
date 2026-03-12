import { useState, useEffect, useRef } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { glossaryTerms } from '../lib/glossary'
import { useTheme } from '../lib/theme'

interface HelpTooltipProps {
  term: string
}

export default function HelpTooltip({ term }: HelpTooltipProps) {
  const [open, setOpen] = useState(false)
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const ref = useRef<HTMLSpanElement>(null)

  const entry = glossaryTerms[term]
  if (!entry) return null

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  return (
    <span ref={ref} className="relative inline-flex items-center ml-1">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(!open) }}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-sky-400 hover:text-sky-300 hover:bg-sky-500/20 transition-colors align-middle"
        title={`Learn about ${entry.short || entry.term}`}
        aria-label={`Help: ${entry.term}`}
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div
          className={`absolute z-50 w-72 rounded-xl border shadow-2xl p-4 mt-1 left-0 top-5 ${
            isDark
              ? 'bg-slate-900 border-slate-700 text-slate-200'
              : 'bg-white border-slate-200 text-slate-800'
          }`}
          style={{ boxShadow: isDark ? '0 8px 32px rgba(0,0,0,0.5)' : '0 8px 32px rgba(0,0,0,0.12)' }}
        >
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`font-semibold text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                {entry.term}
              </span>
              {entry.short && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30 font-mono">
                  {entry.short}
                </span>
              )}
            </div>
            <button
              onClick={() => setOpen(false)}
              className={`shrink-0 ${isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'}`}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className={`text-xs leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
            {entry.definition}
          </p>
          {entry.example && (
            <p className={`text-xs mt-2 italic ${isDark ? 'text-slate-500' : 'text-slate-500'}`}>
              Example: {entry.example}
            </p>
          )}
        </div>
      )}
    </span>
  )
}
