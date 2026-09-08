import { motion, useReducedMotion } from 'motion/react'

import type { CommunityOverlayTheme } from '@/api/communityOverlay'

import {
  CARD_EASE_OUT,
  CardHologram,
  getOverlayThemeStyle,
  MysticCardBackPattern,
} from './CardVisualPrimitives'

import styles from './TarotCard.module.css'

export interface TarotCardEvent {
  actor_display_name: string | null
  payload: {
    card_id: string
    card_name: string
    card_name_en: string
    orientation: 'upright' | 'reversed'
    orientation_label: string
    category: string
    category_label: string
    keywords: string[]
    meaning: string
    advice: string
    image_path: string
    deck_id: string
    deck_version: number
    preview?: boolean
  }
}

interface TarotCardProps {
  event: TarotCardEvent
  theme: CommunityOverlayTheme
  previewLabel?: string
}

function getRevealMotion(theme: CommunityOverlayTheme, reducedMotion: boolean) {
  const disabled = reducedMotion || theme.motion === 'none'

  if (disabled) {
    return {
      disabled: true,
      stageInitial: false as const,
      stageAnimate: { opacity: 1, transform: 'translate3d(0, 0, 0) scale(1)' },
      stageExit: { opacity: 0 },
      stageTransition: { duration: 0.16 },
      flipperInitial: false as const,
      flipperAnimate: { transform: 'rotateY(180deg)' },
      flipperTransition: { duration: 0 },
      parallaxAnimate: { transform: 'rotateX(0deg) rotateY(0deg) rotateZ(0deg)' },
      parallaxTransition: { duration: 0 },
    }
  }

  const subtle = theme.motion === 'subtle'
  return {
    disabled: false,
    stageInitial: {
      opacity: 0,
      transform: subtle
        ? 'translate3d(12px, 18px, 0) scale(0.94) rotateZ(1.5deg)'
        : 'translate3d(28px, 44px, 0) scale(0.84) rotateZ(4deg)',
    },
    stageAnimate: { opacity: 1, transform: 'translate3d(0, 0, 0) scale(1) rotateZ(0deg)' },
    stageExit: {
      opacity: 0,
      transform: subtle
        ? 'translate3d(5px, 8px, 0) scale(0.98)'
        : 'translate3d(10px, 16px, 0) scale(0.96)',
    },
    stageTransition: { duration: subtle ? 0.36 : 0.58, ease: CARD_EASE_OUT },
    flipperInitial: { transform: 'rotateY(0deg)' },
    flipperAnimate: { transform: 'rotateY(180deg)' },
    flipperTransition: {
      delay: subtle ? 0.2 : 0.34,
      duration: subtle ? 0.58 : 0.78,
      ease: CARD_EASE_OUT,
    },
    parallaxAnimate: {
      transform: subtle
        ? [
            'rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
            'rotateX(-2deg) rotateY(3deg) rotateZ(-0.4deg)',
            'rotateX(1.5deg) rotateY(-2deg) rotateZ(0.3deg)',
            'rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
          ]
        : [
            'rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
            'rotateX(-5deg) rotateY(7deg) rotateZ(-1deg)',
            'rotateX(4deg) rotateY(-6deg) rotateZ(0.8deg)',
            'rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
          ],
    },
    parallaxTransition: {
      delay: subtle ? 0.76 : 1.02,
      duration: subtle ? 0.72 : 1.14,
      times: [0, 0.3, 0.68, 1],
      ease: CARD_EASE_OUT,
    },
  }
}

export function TarotCard({ event, theme, previewLabel }: TarotCardProps) {
  const reduceMotion = useReducedMotion()
  const { payload } = event
  const actor = event.actor_display_name || '觀眾'
  const reveal = getRevealMotion(theme, Boolean(reduceMotion))
  const themeStyle = getOverlayThemeStyle(theme)

  return (
    <motion.section
      data-overlay-card
      data-motion={theme.motion}
      data-testid="tarot-reveal"
      data-virtual-pointer={reveal.disabled ? 'off' : 'scripted'}
      className={styles.scene}
      style={themeStyle}
      aria-label={`${actor} 的每日塔羅：${payload.card_name}${payload.orientation_label}`}
      initial={reveal.stageInitial}
      animate={reveal.stageAnimate}
      exit={reveal.stageExit}
      transition={reveal.stageTransition}
    >
      <motion.div
        className={styles.parallax}
        animate={reveal.parallaxAnimate}
        transition={reveal.parallaxTransition}
      >
        <motion.div
          data-testid="tarot-flipper"
          data-reveal-state={reveal.disabled ? 'face' : 'animated'}
          className={styles.flipper}
          initial={reveal.flipperInitial}
          animate={reveal.flipperAnimate}
          transition={reveal.flipperTransition}
        >
          <div
            data-testid="tarot-card-back"
            className={`${styles.face} ${styles.back}`}
            aria-hidden="true"
          >
            <MysticCardBackPattern />
          </div>

          <div className={`${styles.face} ${styles.front}`}>
            <img
              data-testid="tarot-artwork"
              data-orientation={payload.orientation}
              className={styles.artwork}
              src={payload.image_path}
              alt={`${payload.card_name}${payload.orientation_label}`}
            />
            <CardHologram animated={!reveal.disabled} testId="tarot-hologram" />
          </div>
        </motion.div>
      </motion.div>

      {(previewLabel || payload.preview) && (
        <span className={styles.previewBadge}>{previewLabel || 'PREVIEW'}</span>
      )}
    </motion.section>
  )
}
