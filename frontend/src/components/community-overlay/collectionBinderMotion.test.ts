import { describe, expect, it } from 'vitest'

import { DEFAULT_COMMUNITY_OVERLAY_THEME } from '@/api/communityOverlay'

import {
  buildCollectionBinderMotion,
  calculateCardFlightGeometry,
  COLLECTION_BINDER_PHASES,
  COLLECTION_BINDER_TIMELINE,
  getCollectionBinderPlaybackLifetimeMs,
  getOverlayPlaybackLifetimeMs,
} from './collectionBinderMotion'

describe('collection binder timeline', () => {
  it('maps the default theme to a strictly ordered closed-open-card-insert-close story', () => {
    const motion = buildCollectionBinderMotion(DEFAULT_COMMUNITY_OVERLAY_THEME, false, false)

    expect(motion.durationSeconds).toBe(5)
    expect(COLLECTION_BINDER_PHASES).toMatchObject({
      closedHoldEnd: 0.14,
      openEnd: 0.32,
      cardStart: 0.34,
      cardReveal: 0.46,
      insertStart: 0.5,
      insertEnd: 0.58,
      closeStart: 0.82,
      closeEnd: 0.94,
    })
    expect(COLLECTION_BINDER_PHASES.closedHoldEnd).toBeLessThan(COLLECTION_BINDER_PHASES.openEnd)
    expect(COLLECTION_BINDER_PHASES.openEnd).toBeLessThan(COLLECTION_BINDER_PHASES.cardStart)
    expect(COLLECTION_BINDER_PHASES.cardReveal).toBeLessThan(COLLECTION_BINDER_PHASES.insertStart)
    expect(COLLECTION_BINDER_PHASES.insertEnd).toBeLessThan(COLLECTION_BINDER_PHASES.closeStart)
    expect(COLLECTION_BINDER_PHASES.insertEnd).toBeLessThan(COLLECTION_BINDER_PHASES.handoffEnd)
    expect(COLLECTION_BINDER_PHASES.handoffEnd).toBeLessThan(COLLECTION_BINDER_PHASES.closeStart)
    expect(COLLECTION_BINDER_TIMELINE.bookX.output).toEqual([
      '-25%',
      '-25%',
      '0%',
      '0%',
      '-25%',
      '-25%',
    ])
    expect(COLLECTION_BINDER_TIMELINE.coverRotateY.output).toEqual([0, 0, -180, -180, 0, 0])
    expect(COLLECTION_BINDER_TIMELINE).not.toHaveProperty('pagesClipPath')
    expect(COLLECTION_BINDER_TIMELINE.cardTravel.output).toEqual([0, 0, 0, 0, 1, 1])
    expect(COLLECTION_BINDER_TIMELINE.cardScale.standard).toEqual([0.72, 0.72, 1.08, 1])
    expect(COLLECTION_BINDER_TIMELINE.cardOpacity.output.at(-1)).toBe(0)
    expect(COLLECTION_BINDER_TIMELINE.slotCardOpacity.output).toEqual([0, 0, 1, 1])
    expect(
      (COLLECTION_BINDER_PHASES.closeStart - COLLECTION_BINDER_PHASES.insertEnd) *
        motion.durationSeconds
    ).toBeGreaterThanOrEqual(1.2)
    expect(motion.durationSeconds).toBe(5)
  })

  it.each([
    {
      name: 'wide',
      book: { left: 30, top: 480, width: 660, height: 400 },
      origin: { left: 436, top: 536, width: 164, height: 247 },
      target: { left: 84, top: 595, width: 53, height: 79 },
    },
    {
      name: 'narrow',
      book: { left: 16, top: 220, width: 440, height: 267 },
      origin: { left: 292, top: 258, width: 112, height: 169 },
      target: { left: 50, top: 292, width: 38, height: 57 },
    },
  ])(
    'derives an exact $name viewport flight from rendered geometry',
    ({ book, origin, target }) => {
      const flight = calculateCardFlightGeometry(book, origin, target)
      const finalCenterX = flight.left + origin.width / 2 + flight.x
      const finalCenterY = flight.top + origin.height / 2 + flight.y

      expect(finalCenterX).toBeCloseTo(target.left - book.left + target.width / 2)
      expect(finalCenterY).toBeCloseTo(target.top - book.top + target.height / 2)
      expect(origin.width * flight.scale).toBeLessThanOrEqual(target.width)
      expect(origin.height * flight.scale).toBeLessThanOrEqual(target.height)
    }
  )

  it('protects the complete five-second ritual and leaves a paint buffer before unmount', () => {
    const shortTheme = { ...DEFAULT_COMMUNITY_OVERLAY_THEME, display_ms: 2_000 }
    const motion = buildCollectionBinderMotion(shortTheme, false, false)

    expect(motion.durationSeconds).toBe(5)
    expect(getCollectionBinderPlaybackLifetimeMs(shortTheme.display_ms)).toBe(5_100)
    expect(getCollectionBinderPlaybackLifetimeMs(8_000)).toBe(8_100)
    expect(getOverlayPlaybackLifetimeMs('checkin-card', 2_000)).toBe(2_000)
    expect(getOverlayPlaybackLifetimeMs('tarot-card', 2_000)).toBe(2_000)
    expect(
      (COLLECTION_BINDER_PHASES.closeStart - COLLECTION_BINDER_PHASES.insertEnd) *
        motion.durationSeconds
    ).toBeGreaterThanOrEqual(1.2)
  })

  it('resolves OS reduced motion and editor presentation mode directly to the final state', () => {
    expect(buildCollectionBinderMotion(DEFAULT_COMMUNITY_OVERLAY_THEME, true, false).disabled).toBe(
      true
    )
    expect(buildCollectionBinderMotion(DEFAULT_COMMUNITY_OVERLAY_THEME, false, true).disabled).toBe(
      true
    )
  })
})
