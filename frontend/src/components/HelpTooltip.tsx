import React, { useState, useEffect, useRef, useCallback } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { glossaryTerms } from '../lib/glossary'
import { useTheme } from '../lib/theme'

interface HelpTooltipProps {
  term: string
}

interface Position {
  top: number
  left: number
  placement: 'below' | 'above'
}

const TOOLTIP_WIDTH = 288  // w-72 = 18rem = 288px
const TOOLTIP_APPROX_HEIGHT = 160
const SCREEN_PADDING = 12

export default function HelpTooltip({ term }: HelpTooltipProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<Position | null>(null)
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const btnRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const entry = glossaryTerms[term]
  if (!entry) return null

  const isMobile = () => window.innerWidth < 640

  const calculatePosition = useCallback(() => {
    if (!btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight

    // Horizontal: try to align left edge with button, clamp to screen
    let left = rect.left
    if (left + TOOLTIP_WIDTH + SCREEN_PADDING > vw) {
      left = vw - TOOLTIP_WIDTH - SCREEN_PADDING
    }
    if (left < SCREEN_PADDING) left = SCREEN_PADDING

    // Vertical: prefer below, flip above if not enough room
    const spaceBelow = vh - rect.bottom
    const placement: 'below' | 'above' = spaceBelow >= TOOLTIP_APPROX_HEIGHT + 8 ? 'below' : 'above'
    const top = placement === 'below' ? rect.bottom + 6 : rect.top - 6

    setPos({ top, left, placement })
  }, [])

  useEffect(() => {
    if (!open) { setPos(null); return }
    calculatePosition()
    window.addEventListener('resize', calculatePosition)
    window.addEventListener('scroll', calculatePosition, true)
    return () => {
      window.removeEventListener('resize', calculatePosition)
      window.removeEventListener('scroll', calculatePosition, true)
    }
  }, [open, calculatePosition])

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node
      if (
        btnRef.current && !btnRef.current.contains(target) &&
        panelRef.current && !panelRef.current.contains(target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('touchstart', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [open])

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setOpen(prev => !prev)
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={handleToggle}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 hover:bg-sky-500/20 transition-colors align-middle ml-1 shrink-0"
        title={`Learn about ${entry.short || entry.term}`}
        aria-label={`Help: ${entry.term}`}
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>

      {open && (
        <>
          {/* On mobile: dim overlay so the tooltip stands out */}
          {isMobile() && (
            <div
              className="fixed inset-0 z-40 bg-black/20"
              onClick={() => setOpen(false)}
            />
          )}

          {/* Tooltip panel — fixed so it's always viewport-relative */}
          <div
            ref={panelRef}
            className={`fixed z-50 rounded-xl border shadow-2xl p-4 ${
              isDark
                ? 'bg-slate-900 border-slate-700 text-slate-200'
                : 'bg-white border-slate-200 text-slate-800'
            }`}
            style={{
              width: `min(${TOOLTIP_WIDTH}px, calc(100vw - ${SCREEN_PADDING * 2}px))`,
              top: pos
                ? pos.placement === 'below'
                  ? pos.top
                  : undefined
                : undefined,
              bottom: pos
                ? pos.placement === 'above'
                  ? window.innerHeight - pos.top
                  : undefined
                : undefined,
              left: pos ? pos.left : SCREEN_PADDING,
              boxShadow: isDark
                ? '0 8px 32px rgba(0,0,0,0.6)'
                : '0 8px 32px rgba(0,0,0,0.14)',
            }}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`font-semibold text-sm ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                  {entry.term}
                </span>
                {entry.short && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-700 dark:text-sky-400 border border-sky-500/30 font-mono">
                    {entry.short}
                  </span>
                )}
              </div>
              <button
                onClick={() => setOpen(false)}
                className={`shrink-0 p-1 rounded transition-colors ${
                  isDark ? 'text-slate-500 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'
                }`}
                aria-label="Close"
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
        </>
      )}
    </>
  )
}
