import type { CommunityOverlayTheme } from '@/api/communityOverlay'

export const COLLECTION_BINDER_CHOREOGRAPHY_MS = 5_000
export const COLLECTION_BINDER_PAINT_BUFFER_MS = 100

export interface BinderRect {
  left: number
  top: number
  width: number
  height: number
}

export interface CardFlightGeometry {
  left: number
  top: number
  width: number
  height: number
  x: number
  y: number
  scale: number
}

export function calculateCardFlightGeometry(
  book: BinderRect,
  origin: BinderRect,
  target: BinderRect,
  viewportScale = 1
): CardFlightGeometry {
  const normalizedScale = Number.isFinite(viewportScale) && viewportScale > 0 ? viewportScale : 1
  const originCenterX = origin.left + origin.width / 2
  const originCenterY = origin.top + origin.height / 2
  const targetCenterX = target.left + target.width / 2
  const targetCenterY = target.top + target.height / 2
  const insertionScale =
    origin.width > 0 && origin.height > 0
      ? Math.min(target.width / origin.width, target.height / origin.height)
      : 1

  return {
    left: (origin.left - book.left) / normalizedScale,
    top: (origin.top - book.top) / normalizedScale,
    width: origin.width / normalizedScale,
    height: origin.height / normalizedScale,
    x: (targetCenterX - originCenterX) / normalizedScale,
    y: (targetCenterY - originCenterY) / normalizedScale,
    scale: insertionScale,
  }
}

export function getCollectionBinderChoreographyDurationMs(configuredDisplayMs: number): number {
  return Math.max(configuredDisplayMs, COLLECTION_BINDER_CHOREOGRAPHY_MS)
}

export function getCollectionBinderPlaybackLifetimeMs(configuredDisplayMs: number): number {
  return (
    getCollectionBinderChoreographyDurationMs(configuredDisplayMs) +
    COLLECTION_BINDER_PAINT_BUFFER_MS
  )
}

export function getOverlayPlaybackLifetimeMs(
  rendererId: 'checkin-card' | 'collection-binder' | 'tarot-card',
  configuredDisplayMs: number
): number {
  return rendererId === 'collection-binder'
    ? getCollectionBinderPlaybackLifetimeMs(configuredDisplayMs)
    : configuredDisplayMs
}

export const COLLECTION_BINDER_PHASES = {
  closedHoldEnd: 0.14,
  openEnd: 0.32,
  printStart: 0.33,
  printPeak: 0.4,
  printFade: 0.47,
  printEnd: 0.52,
  cardStart: 0.34,
  cardReveal: 0.46,
  insertStart: 0.5,
  insertEnd: 0.58,
  handoffEnd: 0.6,
  closeStart: 0.82,
  closeEnd: 0.94,
} as const

const bookInput = [
  0,
  COLLECTION_BINDER_PHASES.closedHoldEnd,
  COLLECTION_BINDER_PHASES.openEnd,
  COLLECTION_BINDER_PHASES.closeStart,
  COLLECTION_BINDER_PHASES.closeEnd,
  1,
]

const cardInput = [
  0,
  COLLECTION_BINDER_PHASES.cardStart,
  COLLECTION_BINDER_PHASES.cardReveal,
  COLLECTION_BINDER_PHASES.insertStart,
  COLLECTION_BINDER_PHASES.insertEnd,
  1,
]

export const COLLECTION_BINDER_TIMELINE = {
  sceneOpacity: { input: [0, 0.04, 1], output: [0, 1, 1] },
  sceneY: { input: [0, 0.05, 1] },
  sceneScale: { input: [0, 0.05, 1] },
  bookX: {
    input: bookInput,
    output: ['-25%', '-25%', '0%', '0%', '-25%', '-25%'],
  },
  coverRotateY: { input: bookInput, output: [0, 0, -180, -180, 0, 0] },
  printOpacity: {
    input: [
      0,
      COLLECTION_BINDER_PHASES.printStart,
      COLLECTION_BINDER_PHASES.printPeak,
      COLLECTION_BINDER_PHASES.printFade,
      COLLECTION_BINDER_PHASES.printEnd,
      1,
    ],
    output: [0, 0, 1, 0.55, 0, 0],
  },
  printScale: {
    input: [
      0,
      COLLECTION_BINDER_PHASES.printStart,
      COLLECTION_BINDER_PHASES.printPeak,
      COLLECTION_BINDER_PHASES.printFade,
      COLLECTION_BINDER_PHASES.printEnd,
      1,
    ],
    output: [0.45, 0.45, 1, 1.38, 1.55, 1.55],
  },
  cardOpacity: {
    input: [
      0,
      COLLECTION_BINDER_PHASES.cardStart,
      COLLECTION_BINDER_PHASES.cardReveal,
      COLLECTION_BINDER_PHASES.insertEnd,
      COLLECTION_BINDER_PHASES.handoffEnd,
      1,
    ],
    output: [0, 0, 1, 1, 0, 0],
  },
  slotCardOpacity: {
    input: [0, COLLECTION_BINDER_PHASES.insertEnd, COLLECTION_BINDER_PHASES.handoffEnd, 1],
    output: [0, 0, 1, 1],
  },
  cardTravel: {
    input: cardInput,
    output: [0, 0, 0, 0, 1, 1],
  },
  cardScale: {
    input: [0, COLLECTION_BINDER_PHASES.cardStart, COLLECTION_BINDER_PHASES.cardReveal, 1],
    standard: [0.72, 0.72, 1.08, 1],
    subtle: [0.72, 0.72, 1.02, 1],
  },
  cardFlipRotateY: {
    input: [0, COLLECTION_BINDER_PHASES.cardStart, COLLECTION_BINDER_PHASES.cardReveal, 1],
    output: [0, 0, 180, 180],
  },
}

export function buildCollectionBinderMotion(
  theme: CommunityOverlayTheme,
  prefersReducedMotion: boolean,
  staticPreview: boolean
) {
  const disabled = prefersReducedMotion || theme.motion === 'none' || staticPreview
  const durationSeconds = getCollectionBinderChoreographyDurationMs(theme.display_ms) / 1_000
  return {
    disabled,
    durationSeconds,
    sceneExit: { opacity: 0, transition: { duration: 0 } },
  }
}
