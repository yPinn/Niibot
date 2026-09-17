import { useCallback, useMemo, useRef, useState } from 'react'

import type { Crosshair } from '@/api/crosshairs'
import { cn } from '@/lib/utils'

import { CrosshairAdjustSheet } from './CrosshairAdjustSheet'
import { CrosshairPreview, CrosshairSVG } from './CrosshairPreview'
import { decodeValorantCrosshair, VALORANT_DEFAULTS } from './valorantDecode'

interface ShootingRangeProps {
  crosshairs: Crosshair[]
  onSave: (id: string, code: string) => void
}

export function ShootingRange({ crosshairs, onSave }: ShootingRangeProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [adjOpen, setAdjOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)

  const active = crosshairs.find(c => c.id === activeId) ?? null
  const params = useMemo(
    () => (active ? decodeValorantCrosshair(active.code) : VALORANT_DEFAULTS),
    [active]
  )

  const handleSelect = useCallback(
    (id: string) => {
      if (activeId === id) setAdjOpen(true)
      else setActiveId(id)
    },
    [activeId]
  )

  const handleAdjSave = useCallback(
    (code: string) => {
      if (activeId) onSave(activeId, code)
    },
    [activeId, onSave]
  )

  const moveCursorTo = useCallback((clientX: number, clientY: number) => {
    if (!cursorRef.current || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    cursorRef.current.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%)`
  }, [])

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => moveCursorTo(e.clientX, e.clientY),
    [moveCursorTo]
  )

  const handleMouseEnter = useCallback(() => {
    if (cursorRef.current && activeId) cursorRef.current.style.opacity = '1'
  }, [activeId])

  const handleMouseLeave = useCallback(() => {
    if (cursorRef.current) cursorRef.current.style.opacity = '0'
  }, [])

  // Touch equivalents — no pointer to hover, so a touch positions the
  // cursor and shows it immediately (start) and hides it on release (end).
  const handleTouchMove = useCallback(
    (e: React.TouchEvent<HTMLDivElement>) => {
      const touch = e.touches[0]
      if (touch) moveCursorTo(touch.clientX, touch.clientY)
    },
    [moveCursorTo]
  )

  const handleTouchStart = useCallback(
    (e: React.TouchEvent<HTMLDivElement>) => {
      handleTouchMove(e)
      if (cursorRef.current && activeId) cursorRef.current.style.opacity = '1'
    },
    [handleTouchMove, activeId]
  )

  const handleTouchEnd = useCallback(() => {
    if (cursorRef.current) cursorRef.current.style.opacity = '0'
  }, [])

  const handleClick = useCallback(() => {
    new Audio('/audio/phantom_sfx.mp3').play().catch(() => {})
  }, [])

  return (
    <>
      <div className="flex flex-1 min-h-0 flex-col gap-section">
        {/* Crosshair selector */}
        <div className="flex shrink-0 flex-wrap gap-element">
          {crosshairs.map(c => (
            <button
              key={c.id}
              onClick={() => handleSelect(c.id)}
              className={cn(
                'flex flex-col items-center gap-1 rounded-lg border-2 p-element transition-colors',
                activeId === c.id
                  ? 'border-primary bg-primary/10'
                  : 'border-muted-foreground/30 hover:border-muted-foreground/60'
              )}
            >
              <CrosshairPreview game={c.game} code={c.code} size="sm" />
              <span className="max-w-[56px] truncate text-label text-muted-foreground">
                {c.name}
              </span>
            </button>
          ))}
          {crosshairs.length === 0 && (
            <p className="text-sub text-muted-foreground">尚無準星，請先在「我的」頁面新增</p>
          )}
        </div>

        {/* Range block — fills remaining height */}
        <div
          ref={containerRef}
          className="relative min-h-0 flex-1 overflow-hidden rounded-xl border-2 border-muted-foreground/50"
          style={{
            cursor: activeId ? 'none' : 'default',
            backgroundImage: 'url(/images/valorant_map.jpg)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
          onMouseMove={handleMouseMove}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onTouchMove={handleTouchMove}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          onClick={handleClick}
        >
          {!activeId && (
            <div className="absolute left-3 top-3 rounded-md bg-black/60 px-element py-1 backdrop-blur-sm">
              <p className="text-sub text-white/90">選擇一個準星開始模擬</p>
            </div>
          )}

          <div
            ref={cursorRef}
            className="pointer-events-none absolute left-0 top-0 opacity-0"
            style={{ willChange: 'transform' }}
          >
            <CrosshairSVG p={params} size="actual" />
          </div>
        </div>
      </div>

      <CrosshairAdjustSheet
        key={activeId ?? ''}
        open={adjOpen}
        onOpenChange={setAdjOpen}
        initialCode={active?.code ?? ''}
        onSave={handleAdjSave}
        overlayClassName="bg-black/20"
      />
    </>
  )
}
