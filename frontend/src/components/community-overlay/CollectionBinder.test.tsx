import { fireEvent, render, screen } from '@testing-library/react'
import type * as MotionReact from 'motion/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DEFAULT_COMMUNITY_OVERLAY_THEME } from '@/api/communityOverlay'

import { resolveSameOriginArtwork } from './artwork'
import { CollectionBinder } from './CollectionBinder'

const reducedMotion = vi.hoisted(() => ({ value: false }))

vi.mock('motion/react', async () => {
  const actual = await vi.importActual<typeof MotionReact>('motion/react')
  return { ...actual, useReducedMotion: () => reducedMotion.value }
})

const COLLECTION = {
  draw_id: 17,
  pool_revision_id: 3,
  algorithm_version: 'weighted-rarity-v1',
  card: {
    id: 11,
    revision_id: 2,
    key: 'moonlit-compass',
    number: 'GI-011',
    name: '月巡羅盤',
    artwork: {
      portrait_url: '/images/collections/starter/moonlit-compass.webp',
      square_url: null,
      backdrop_url: null,
    },
  },
  set: { id: 1, key: 'starter-isles', name: '浮游群島' },
  rarity: { key: 'rare', label: '稀有', rank: 2, effect_intensity: 50 },
  is_new: true,
  copy_count: 1,
  progress: { owned_copies: 8, unique_cards: 6, total_cards: 24 },
}

function binderEvent(overrides: Record<string, unknown> = {}) {
  return {
    actor_display_name: 'Alice',
    payload: {
      total_days: 8,
      checkin_date: '2026-09-08',
      collection: { ...COLLECTION, ...overrides },
    },
  }
}

describe('CollectionBinder', () => {
  beforeEach(() => {
    reducedMotion.value = false
  })

  it('presents one viewer-scoped closed-open-card-insert-close reveal', () => {
    render(<CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    expect(screen.getByTestId('collection-binder')).toHaveAttribute(
      'data-animation-sequence',
      'closed open card insert close'
    )
    expect(
      screen.getByRole('status', {
        name: 'Alice 的卡冊：獲得稀有卡月巡羅盤',
      })
    ).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByTestId('binder-book')).toHaveAttribute('data-phase', 'closed open close')
    expect(screen.getByTestId('binder-book')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByTestId('binder-cover')).toHaveAttribute('data-phase', 'closed open close')
    expect(screen.getByTestId('binder-pages')).toHaveAttribute('data-phase', 'open close')
    expect(screen.getByTestId('binder-print')).toHaveAttribute('data-phase', 'print')
    expect(screen.getByTestId('binder-card-stage')).toHaveAttribute('data-presentation', 'featured')
    expect(screen.getByTestId('collection-card')).toHaveAttribute('data-phase', 'card insert')
    expect(screen.getByTestId('binder-slot')).toHaveAttribute('data-phase', 'insert')
    expect(screen.getByTestId('binder-slot-card')).toHaveAttribute('data-phase', 'handoff close')
    expect(screen.getByText('月巡羅盤')).toBeInTheDocument()
    expect(screen.getByText('GI-011')).toBeInTheDocument()
    expect(screen.getAllByText('浮游群島')).toHaveLength(2)
    expect(screen.getByText('稀有')).toBeInTheDocument()
    expect(screen.getByText('NEW')).toBeInTheDocument()
    expect(screen.getByText('6 / 24')).toBeInTheDocument()
    expect(screen.getByTestId('binder-progress')).toBeInTheDocument()
    expect(screen.queryByText('CARD ARCHIVE')).not.toBeInTheDocument()
    expect(screen.getByTestId('card-artwork')).toHaveAttribute(
      'src',
      COLLECTION.card.artwork.portrait_url
    )
  })

  it('models the cover and collection page as one registered two-sided leaf', () => {
    render(<CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    const leafStack = screen.getByTestId('binder-leaf-stack')
    const pages = screen.getByTestId('binder-pages')
    const cover = screen.getByTestId('binder-cover')
    const coverOuter = screen.getByTestId('binder-cover-outer')
    const coverInner = screen.getByTestId('binder-cover-inner')
    const leftPage = screen.getByTestId('binder-left-page')
    const rightPage = screen.getByTestId('binder-right-page')

    expect(leafStack).toContainElement(pages)
    expect(leafStack).toContainElement(cover)
    expect(cover).toContainElement(coverOuter)
    expect(cover).toContainElement(coverInner)
    expect(coverInner).toContainElement(leftPage)
    expect(pages).toContainElement(rightPage)
    expect(pages).not.toContainElement(leftPage)
    expect(pages.getAttribute('style') ?? '').not.toContain('clip-path')
  })

  it('preserves the two-row slot geometry on narrow screens so insertion stays aligned', () => {
    const styles = readFileSync(resolve(import.meta.dirname, 'CollectionBinder.module.css'), 'utf8')
    const narrowScreenRule = styles.match(/@media \(max-width: 520px\) \{([\s\S]*?)\n\}/)?.[1]

    expect(narrowScreenRule).toContain('grid-template-rows: repeat(2, minmax(0, 1fr));')
    expect(narrowScreenRule).not.toContain('grid-template-rows: minmax(0, 1fr);')
  })

  it('lets the generated card travel beyond the right-page leaf into the left slot', () => {
    render(<CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    expect(screen.getByTestId('binder-book')).toContainElement(
      screen.getByTestId('collection-card')
    )
    expect(screen.getByTestId('binder-leaf-stack')).not.toContainElement(
      screen.getByTestId('collection-card')
    )
  })

  it('shows an isolated duplicate result without retaining another viewer state', () => {
    const { rerender } = render(
      <CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />
    )

    rerender(
      <CollectionBinder
        event={{
          actor_display_name: 'Bob',
          payload: {
            total_days: 13,
            checkin_date: '2026-09-08',
            collection: { ...COLLECTION, is_new: false, copy_count: 3 },
          },
        }}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(
      screen.getByRole('status', { name: 'Bob 的卡冊：獲得稀有卡月巡羅盤' })
    ).toBeInTheDocument()
    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-result', 'duplicate')
    expect(screen.getByText('×3')).toBeInTheDocument()
    expect(screen.queryByText('NEW')).not.toBeInTheDocument()
    expect(screen.queryByText('@Alice')).not.toBeInTheDocument()
  })

  it.each([
    ['common', '普通', 10],
    ['rare', '稀有', 50],
    ['legendary', '傳說', 100],
  ])('keeps rarity %s visible beyond color alone', (key, label, effectIntensity) => {
    render(
      <CollectionBinder
        event={binderEvent({
          rarity: { key, label, rank: effectIntensity, effect_intensity: effectIntensity },
        })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(screen.getByTestId('collection-card')).toHaveAttribute('data-rarity', key)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('uses only same-origin artwork and falls back after an image decode failure', () => {
    expect(resolveSameOriginArtwork('/images/collections/card.webp', 'https://niibot.test')).toBe(
      '/images/collections/card.webp'
    )
    expect(
      resolveSameOriginArtwork('/images/collections/card.webp', 'https://niibot.test/app/')
    ).toBe('/images/collections/card.webp')
    expect(
      resolveSameOriginArtwork(
        'https://niibot.test/images/collections/card.webp',
        'https://niibot.test'
      )
    ).toBeNull()
    expect(
      resolveSameOriginArtwork('/images/collections/%2e%2e/api/private.webp', 'https://niibot.test')
    ).toBeNull()
    expect(
      resolveSameOriginArtwork('/images/collections/card.svg', 'https://niibot.test')
    ).toBeNull()
    expect(
      resolveSameOriginArtwork('/images/collections/card.webp?token=x', 'https://niibot.test')
    ).toBeNull()
    expect(
      resolveSameOriginArtwork('/images/collections/card.webp#fragment', 'https://niibot.test')
    ).toBeNull()
    expect(resolveSameOriginArtwork('/api/private.webp', 'https://niibot.test')).toBeNull()
    expect(
      resolveSameOriginArtwork('//evil.test/images/collections/card.webp', 'https://niibot.test')
    ).toBeNull()
    expect(resolveSameOriginArtwork('data:image/png;base64,AA==', 'https://niibot.test')).toBeNull()

    render(
      <CollectionBinder
        event={binderEvent({
          card: {
            ...COLLECTION.card,
            artwork: {
              portrait_url: 'https://evil.test/tracker.gif',
              square_url: '/images/collections/safe.webp',
              backdrop_url: null,
            },
          },
        })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    const artwork = screen.getByTestId('card-artwork')
    expect(artwork).toHaveAttribute('src', '/images/collections/safe.webp')
    fireEvent.error(artwork)
    expect(screen.getByTestId('card-artwork')).toHaveAttribute('aria-label', '月巡羅盤圖片尚未提供')
  })

  it('renders the final readable state without staged motion when animation is disabled', () => {
    render(
      <CollectionBinder
        event={binderEvent()}
        theme={{ ...DEFAULT_COMMUNITY_OVERLAY_THEME, motion: 'none' }}
      />
    )

    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-motion-state', 'final')
    expect(
      screen.getByRole('status', {
        name: 'Alice 的卡冊：獲得稀有卡月巡羅盤',
      })
    ).toBeInTheDocument()
    expect(screen.getByText('月巡羅盤')).toBeInTheDocument()
  })

  it('keeps the long-lived editor preview open while live previews retain the staged sequence', () => {
    render(
      <CollectionBinder
        event={binderEvent()}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
        previewLabel="草稿預覽"
        staticPreview
      />
    )

    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-motion-state', 'final')
    expect(screen.getByText('草稿預覽')).toHaveAttribute('data-anchor', 'top-right')
  })

  it('uses the final readable state when the operating system requests reduced motion', () => {
    reducedMotion.value = true
    render(<CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-motion-state', 'final')
  })
})
