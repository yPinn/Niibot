import type { CSSProperties } from 'react'
import { motion, useReducedMotion } from 'motion/react'

import type { CommunityOverlayMotion, CommunityOverlayTheme } from '@/api/communityOverlay'

import styles from './CheckinCard.module.css'

const STAMP_COUNT = 7

export interface CheckinCardEvent {
  actor_display_name: string | null
  payload: {
    total_days: number
    checkin_date: string
    preview?: boolean
  }
}

interface CheckinCardProps {
  event: CheckinCardEvent
  theme: CommunityOverlayTheme
  previewLabel?: string
}

interface ThemeStyle extends CSSProperties {
  '--overlay-surface': string
  '--overlay-accent': string
  '--overlay-text': string
  '--overlay-radius': string
}

function cardMotion(motionLevel: CommunityOverlayMotion, disabled: boolean) {
  if (disabled || motionLevel === 'none') {
    return {
      initial: false as const,
      exit: { opacity: 0 },
      transition: { duration: 0 },
    }
  }
  if (motionLevel === 'subtle') {
    return {
      initial: { opacity: 0, transform: 'translateY(10px) scale(0.99)' },
      exit: { opacity: 0, transform: 'translateY(-6px)' },
      transition: { duration: 0.24, ease: [0.16, 1, 0.3, 1] as const },
    }
  }
  return {
    initial: { opacity: 0, transform: 'translateY(28px) scale(0.94)' },
    exit: { opacity: 0, transform: 'translateY(-18px) scale(0.97)' },
    transition: { duration: 0.38, ease: [0.16, 1, 0.3, 1] as const },
  }
}

export function CheckinCard({ event, theme, previewLabel }: CheckinCardProps) {
  const reduceMotion = useReducedMotion()
  const motionDisabled = Boolean(reduceMotion) || theme.motion === 'none'
  const totalDays = event.payload.total_days
  const activeStamp = ((totalDays - 1) % STAMP_COUNT) + 1
  const cycle = Math.floor((totalDays - 1) / STAMP_COUNT) + 1
  const actor = event.actor_display_name || '觀眾'
  const motionConfig = cardMotion(theme.motion, motionDisabled)
  const themeStyle: ThemeStyle = {
    '--overlay-surface': theme.surface_color,
    '--overlay-accent': theme.accent_color,
    '--overlay-text': theme.text_color,
    '--overlay-radius': `${theme.radius_px}px`,
  }

  return (
    <motion.section
      data-overlay-card
      data-motion={theme.motion}
      className={styles.card}
      style={themeStyle}
      aria-label={`${actor} 的簽到集點卡`}
      initial={motionConfig.initial}
      animate={{ opacity: 1, transform: 'translateY(0) scale(1)' }}
      exit={motionConfig.exit}
      transition={motionConfig.transition}
    >
      <div className={styles.header}>
        <div className={styles.identity}>
          <div className={styles.eyebrow}>
            每日簽到
            {(previewLabel || event.payload.preview) && (
              <span className={styles.previewBadge}>{previewLabel || 'DEV PREVIEW'}</span>
            )}
          </div>
          <div className={styles.actor}>@{actor}</div>
        </div>
        <div className={styles.total} aria-label={`累積第 ${totalDays} 天`}>
          <span>累積第</span>
          <strong>{totalDays}</strong>
          <span>天</span>
        </div>
      </div>

      <div className={styles.stamps} aria-label={`第 ${cycle} 張集點卡`}>
        {Array.from({ length: STAMP_COUNT }, (_, index) => {
          const position = index + 1
          const filled = position <= activeStamp
          const isNewest = position === activeStamp
          return (
            <motion.div
              key={position}
              data-testid="checkin-stamp"
              data-filled={filled ? 'true' : 'false'}
              className={`${styles.stamp} ${filled ? styles.stampFilled : ''}`}
              initial={
                isNewest && !motionDisabled
                  ? { opacity: 0, transform: 'scale(1.7) rotate(-14deg)' }
                  : false
              }
              animate={{ opacity: 1, transform: 'scale(1) rotate(0deg)' }}
              transition={{
                duration: motionDisabled ? 0 : theme.motion === 'subtle' ? 0.24 : 0.42,
                delay: isNewest && !motionDisabled ? (theme.motion === 'subtle' ? 0.12 : 0.28) : 0,
                ease: [0.34, 1.56, 0.64, 1],
              }}
            >
              {filled ? '✓' : position}
            </motion.div>
          )
        })}
      </div>

      <div className={styles.footer}>
        <span>{event.payload.checkin_date}</span>
        <span>第 {cycle} 張</span>
      </div>
    </motion.section>
  )
}
