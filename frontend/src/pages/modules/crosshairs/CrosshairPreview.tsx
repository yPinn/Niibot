import type { CrosshairGame } from '@/api/crosshairs'

import type { ValorantCrosshairParams } from './valorantDecode'
import { decodeValorantCrosshair, VALORANT_DEFAULTS } from './valorantDecode'

interface CrosshairPreviewProps {
  game: CrosshairGame | string
  code: string
  size?: 'sm' | 'lg'
}

// scale multiplier per size
const SCALE: Record<'sm' | 'lg', number> = { sm: 2.5, lg: 5 }
const CONTAINER: Record<'sm' | 'lg', number> = { sm: 52, lg: 120 }

function resolveParams(game: string, code: string): ValorantCrosshairParams {
  if (game === 'valorant') return decodeValorantCrosshair(code)
  return VALORANT_DEFAULTS
}

export function CrosshairPreview({ game, code, size = 'sm' }: CrosshairPreviewProps) {
  const params = resolveParams(game, code)
  const scale = SCALE[size]
  const container = CONTAINER[size]

  const ll = params.lineLength * scale
  const gap = params.gap * scale
  const thick = Math.max(1, params.thickness * scale)
  const oll = params.outerLinesEnabled ? params.outerLength * scale : 0
  const ogap = params.outerLinesEnabled ? params.outerGap * scale : 0
  const othick = Math.max(1, params.outerThickness * scale)
  const dotR = params.hasDot ? Math.max(1, params.dotSize * scale * 0.5) : 0

  const center = container / 2

  const lineStyle = (
    x: number,
    y: number,
    w: number,
    h: number,
    opacity: number
  ): React.CSSProperties => ({
    position: 'absolute',
    left: x,
    top: y,
    width: w,
    height: h,
    backgroundColor: params.color,
    opacity,
  })

  return (
    <div
      style={{
        position: 'relative',
        width: container,
        height: container,
        backgroundColor: '#1a1a1a',
        borderRadius: size === 'lg' ? 12 : 6,
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      {/* Inner lines */}
      {ll > 0 && (
        <>
          {/* right */}
          <div style={lineStyle(center + gap, center - thick / 2, ll, thick, params.opacity)} />
          {/* left */}
          <div
            style={lineStyle(center - gap - ll, center - thick / 2, ll, thick, params.opacity)}
          />
          {/* bottom */}
          <div style={lineStyle(center - thick / 2, center + gap, thick, ll, params.opacity)} />
          {/* top */}
          <div
            style={lineStyle(center - thick / 2, center - gap - ll, thick, ll, params.opacity)}
          />
        </>
      )}

      {/* Outer lines */}
      {params.outerLinesEnabled && oll > 0 && (
        <>
          <div
            style={lineStyle(center + ogap, center - othick / 2, oll, othick, params.outerOpacity)}
          />
          <div
            style={lineStyle(
              center - ogap - oll,
              center - othick / 2,
              oll,
              othick,
              params.outerOpacity
            )}
          />
          <div
            style={lineStyle(center - othick / 2, center + ogap, othick, oll, params.outerOpacity)}
          />
          <div
            style={lineStyle(
              center - othick / 2,
              center - ogap - oll,
              othick,
              oll,
              params.outerOpacity
            )}
          />
        </>
      )}

      {/* Center dot */}
      {params.hasDot && dotR > 0 && (
        <div
          style={{
            position: 'absolute',
            left: center - dotR,
            top: center - dotR,
            width: dotR * 2,
            height: dotR * 2,
            borderRadius: '50%',
            backgroundColor: params.color,
            opacity: params.opacity,
          }}
        />
      )}
    </div>
  )
}
