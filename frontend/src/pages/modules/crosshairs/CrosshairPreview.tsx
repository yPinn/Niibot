import { memo, useMemo } from 'react'

import type { CrosshairGame } from '@/api/crosshairs'

import type { ValorantCrosshairParams } from './valorantDecode'
import { decodeValorantCrosshair, VALORANT_DEFAULTS } from './valorantDecode'

interface CrosshairPreviewProps {
  game: CrosshairGame | string
  code: string
  size?: 'sm' | 'lg' | 'actual'
}

const BASE_SCALE: Record<'sm' | 'lg', number> = { sm: 2.5, lg: 5 }
const CONTAINER: Record<'sm' | 'lg', number> = { sm: 56, lg: 240 }
const RADIUS: Record<'sm' | 'lg', number> = { sm: 4, lg: 16 }

const PADDING = 0.12
const ACTUAL_SCALE_BASE = 1
const ACTUAL_PAD = 4

function resolveParams(game: string, code: string): ValorantCrosshairParams {
  if (game === 'valorant') return decodeValorantCrosshair(code)
  return VALORANT_DEFAULTS
}

// Outline rendered as 4 separate black rects — avoids rounded corners and opacity
// compositing issues that CSS box-shadow would produce.
const CrosshairRect = memo(function CrosshairRect({
  x,
  y,
  w,
  h,
  color,
  opacity,
  sw,
  oa,
}: {
  x: number
  y: number
  w: number
  h: number
  color: string
  opacity: number
  sw: number
  oa: number
}) {
  return (
    <>
      {sw > 0 && (
        <>
          <rect x={x - sw} y={y - sw} width={sw} height={h + sw * 2} fill="black" opacity={oa} />
          <rect x={x + w} y={y - sw} width={sw} height={h + sw * 2} fill="black" opacity={oa} />
          <rect x={x} y={y - sw} width={w} height={sw} fill="black" opacity={oa} />
          <rect x={x} y={y + h} width={w} height={sw} fill="black" opacity={oa} />
        </>
      )}
      <rect x={x} y={y} width={w} height={h} fill={color} opacity={opacity} />
    </>
  )
})

// Separating decode from render lets CrosshairDetailPreview decode once and reuse
// the same params object for both lg and actual sizes.
const CrosshairSVG = memo(function CrosshairSVG({
  p,
  size = 'sm',
}: {
  p: ValorantCrosshairParams
  size: 'sm' | 'lg' | 'actual'
}) {
  const innerBound = p.showInnerLines
    ? p.innerOffset + Math.max(p.innerLength, p.innerVerticalLength)
    : 0
  const outerBound = p.showOuterLines
    ? p.outerOffset + Math.max(p.outerLength, p.outerVerticalLength)
    : 0
  const dotBound = p.hasDot ? p.dotThickness / 2 : 0
  const extent = Math.max(innerBound, outerBound, dotBound, 1)

  let scale: number
  let container: number
  let radius: number

  if (size === 'actual') {
    scale = ACTUAL_SCALE_BASE
    container = Math.max(4, Math.ceil(extent * 2 * ACTUAL_SCALE_BASE) + ACTUAL_PAD * 2)
    radius = 0
  } else {
    container = CONTAINER[size]
    radius = RADIUS[size]
    const maxRadius = (container / 2) * (1 - PADDING)
    scale = Math.min(BASE_SCALE[size], maxRadius / extent)
  }

  const iThick = Math.max(scale * 0.4, p.innerThickness * scale)
  const iGap = p.innerOffset * scale
  const iLenH = p.innerLength * scale
  const iLenV = p.innerVerticalLength * scale

  const oThick = Math.max(scale * 0.4, p.outerThickness * scale)
  const oGap = p.outerOffset * scale
  const oLenH = p.outerLength * scale
  const oLenV = p.outerVerticalLength * scale

  const dotSide = Math.max(1, p.dotThickness * scale)

  const sw = p.outlines ? Math.max(0.5, p.outlineThickness * scale * 0.25) : 0
  const oa = p.outlineOpacity
  const c = p.color

  return (
    <svg
      width={container}
      height={container}
      style={
        size === 'actual'
          ? { display: 'block', filter: 'drop-shadow(0 0 1px rgba(0,0,0,0.9))' }
          : { borderRadius: radius, flexShrink: 0, display: 'block' }
      }
    >
      <g transform={`translate(${container / 2},${container / 2})`}>
        {p.showInnerLines && (
          <>
            {iLenH > 0 && (
              <>
                <CrosshairRect
                  x={iGap}
                  y={-iThick / 2}
                  w={iLenH}
                  h={iThick}
                  color={c}
                  opacity={p.innerOpacity}
                  sw={sw}
                  oa={oa}
                />
                <CrosshairRect
                  x={-iGap - iLenH}
                  y={-iThick / 2}
                  w={iLenH}
                  h={iThick}
                  color={c}
                  opacity={p.innerOpacity}
                  sw={sw}
                  oa={oa}
                />
              </>
            )}
            {iLenV > 0 && (
              <>
                <CrosshairRect
                  x={-iThick / 2}
                  y={iGap}
                  w={iThick}
                  h={iLenV}
                  color={c}
                  opacity={p.innerOpacity}
                  sw={sw}
                  oa={oa}
                />
                <CrosshairRect
                  x={-iThick / 2}
                  y={-iGap - iLenV}
                  w={iThick}
                  h={iLenV}
                  color={c}
                  opacity={p.innerOpacity}
                  sw={sw}
                  oa={oa}
                />
              </>
            )}
          </>
        )}

        {p.showOuterLines && (
          <>
            {oLenH > 0 && (
              <>
                <CrosshairRect
                  x={oGap}
                  y={-oThick / 2}
                  w={oLenH}
                  h={oThick}
                  color={c}
                  opacity={p.outerOpacity}
                  sw={sw}
                  oa={oa}
                />
                <CrosshairRect
                  x={-oGap - oLenH}
                  y={-oThick / 2}
                  w={oLenH}
                  h={oThick}
                  color={c}
                  opacity={p.outerOpacity}
                  sw={sw}
                  oa={oa}
                />
              </>
            )}
            {oLenV > 0 && (
              <>
                <CrosshairRect
                  x={-oThick / 2}
                  y={oGap}
                  w={oThick}
                  h={oLenV}
                  color={c}
                  opacity={p.outerOpacity}
                  sw={sw}
                  oa={oa}
                />
                <CrosshairRect
                  x={-oThick / 2}
                  y={-oGap - oLenV}
                  w={oThick}
                  h={oLenV}
                  color={c}
                  opacity={p.outerOpacity}
                  sw={sw}
                  oa={oa}
                />
              </>
            )}
          </>
        )}

        {p.hasDot && dotSide > 0 && (
          <CrosshairRect
            x={-dotSide / 2}
            y={-dotSide / 2}
            w={dotSide}
            h={dotSide}
            color={c}
            opacity={p.dotOpacity}
            sw={sw}
            oa={oa}
          />
        )}
      </g>
    </svg>
  )
})

export const CrosshairPreview = memo(function CrosshairPreview({
  game,
  code,
  size = 'sm',
}: CrosshairPreviewProps) {
  const p = useMemo(() => resolveParams(game, code), [game, code])
  return <CrosshairSVG p={p} size={size} />
})

export const CrosshairDetailPreview = memo(function CrosshairDetailPreview({
  game,
  code,
}: {
  game: CrosshairGame | string
  code: string
}) {
  const p = useMemo(() => resolveParams(game, code), [game, code])
  return (
    <div className="flex items-end justify-center gap-empty py-page">
      <div className="flex flex-col items-center gap-element">
        <CrosshairSVG p={p} size="lg" />
        <span className="text-label text-muted-foreground">預覽</span>
      </div>
      <div className="flex flex-col items-center gap-element">
        <div className="flex size-20 items-center justify-center rounded bg-muted">
          <CrosshairSVG p={p} size="actual" />
        </div>
        <span className="text-label text-muted-foreground">實際大小 (1080p)</span>
      </div>
    </div>
  )
})
