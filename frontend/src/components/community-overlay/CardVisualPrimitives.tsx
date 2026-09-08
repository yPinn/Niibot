import type { CSSProperties } from 'react'

import type { CommunityOverlayTheme } from '@/api/communityOverlay'

import styles from './CardVisualPrimitives.module.css'

export const CARD_EASE_OUT = [0.16, 1, 0.3, 1] as const

export interface OverlayThemeStyle extends CSSProperties {
  '--overlay-surface': string
  '--overlay-accent': string
  '--overlay-text': string
  '--overlay-radius': string
}

export function getOverlayThemeStyle(theme: CommunityOverlayTheme): OverlayThemeStyle {
  return {
    '--overlay-surface': theme.surface_color,
    '--overlay-accent': theme.accent_color,
    '--overlay-text': theme.text_color,
    '--overlay-radius': `${theme.radius_px}px`,
  }
}

export function MysticCardBackPattern() {
  return (
    <span className={styles.backField}>
      <span className={styles.backOrbit} />
    </span>
  )
}

export function CardHologram({
  animated = false,
  testId = 'card-hologram',
}: {
  animated?: boolean
  testId?: string
}) {
  return (
    <span
      data-testid={testId}
      className={`${styles.hologram} ${animated ? styles.hologramAnimated : ''}`}
      aria-hidden="true"
    />
  )
}
