import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    number: '005',
    name: '月巡羅盤',
    artwork: {
      portrait_url: '/images/collections/starter/moonlit-compass.webp',
      square_url: null,
      backdrop_url: null,
    },
  },
  set: { id: 1, key: 'aespa', name: 'aespa' },
  rarity: { key: 'rare', label: '稀有', rank: 2, effect_intensity: 50 },
  is_new: true,
  copy_count: 1,
  progress: { owned_copies: 6, unique_cards: 4, total_cards: 11 },
  owned_cards: [
    {
      card: {
        id: 7,
        revision_id: 1,
        key: 'karina-01',
        number: '001',
        name: 'Karina',
        artwork: {
          portrait_url: '/images/collections/aespa/karina-01-r1.webp',
          square_url: null,
          backdrop_url: null,
        },
      },
      rarity: { key: 'common', label: '普通', rank: 1, effect_intensity: 10 },
      copy_count: 2,
    },
    {
      card: {
        id: 8,
        revision_id: 1,
        key: 'winter-01',
        number: '003',
        name: 'Winter',
        artwork: {
          portrait_url: '/images/collections/aespa/winter-01-r1.webp',
          square_url: null,
          backdrop_url: null,
        },
      },
      rarity: { key: 'common', label: '普通', rank: 1, effect_intensity: 10 },
      copy_count: 2,
    },
    {
      card: {
        id: 11,
        revision_id: 2,
        key: 'moonlit-compass',
        number: '005',
        name: '月巡羅盤',
        artwork: {
          portrait_url: '/images/collections/starter/moonlit-compass.webp',
          square_url: null,
          backdrop_url: null,
        },
      },
      rarity: { key: 'rare', label: '稀有', rank: 2, effect_intensity: 50 },
      copy_count: 1,
    },
    {
      card: {
        id: 15,
        revision_id: 1,
        key: 'ningning-02',
        number: '009',
        name: 'Ningning',
        artwork: {
          portrait_url: '/images/collections/aespa/ningning-02-r1.webp',
          square_url: null,
          backdrop_url: null,
        },
      },
      rarity: { key: 'common', label: '普通', rank: 1, effect_intensity: 10 },
      copy_count: 1,
    },
  ],
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

function domRect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    bottom: top + height,
    height,
    left,
    right: left + width,
    top,
    width,
    x: left,
    y: top,
    toJSON: () => ({}),
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
    expect(screen.getByText('005')).toBeInTheDocument()
    expect(screen.getAllByText('aespa')).toHaveLength(1)
    expect(screen.getByText('稀有')).toBeInTheDocument()
    expect(screen.getByText('NEW')).toBeInTheDocument()
    expect(screen.getByText('4 / 11')).toBeInTheDocument()
    expect(screen.getByTestId('binder-page-indicator')).toHaveTextContent('1 / 2')
    expect(screen.getByTestId('binder-progress')).toBeInTheDocument()
    expect(screen.queryByText('@Alice')).not.toBeInTheDocument()
    expect(screen.queryByText('第 8 次簽到')).not.toBeInTheDocument()
    expect(screen.queryByText('本冊共 6 張')).not.toBeInTheDocument()
    expect(screen.queryByText('已登錄至卡冊')).not.toBeInTheDocument()
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

  it('uses a 720 × 480 three-by-three spread without hiding pockets on narrow screens', () => {
    const styles = readFileSync(resolve(import.meta.dirname, 'CollectionBinder.module.css'), 'utf8')
    const narrowScreenRule = styles.match(/@media \(max-width: 520px\) \{([\s\S]*?)\n\}/)?.[1]
    const sceneRule = styles.match(/\.scene \{([\s\S]*?)\n\}/)?.[1]
    const bookRule = styles.match(/\.book \{([\s\S]*?)\n\}/)?.[1]
    const leafStackRule = styles.match(/\.leafStack \{([\s\S]*?)\n\}/)?.[1]
    const pagesRule = styles.match(/\.pages \{([\s\S]*?)\n\}/)?.[1]
    const slotGridRule = styles.match(/\.slotGrid \{([\s\S]*?)\n\}/)?.[1]
    const pageRule = styles.match(/\.page \{([\s\S]*?)\n\}/)?.[1]
    const leftPageRule = styles.match(/\.leftPage \{([\s\S]*?)\n\}/)?.[1]
    const rightPageRule = styles.match(/\.rightPage \{([\s\S]*?)\n\}/)?.[1]
    const cardSlotRule = styles.match(/\.cardSlot \{([\s\S]*?)\n\}/)?.[1]
    const coverInnerRule = styles.match(/\.coverInner \{([\s\S]*?)\n\}/)?.[1]
    const coverFaceRule = styles.match(/\.coverFace \{([\s\S]*?)\n\}/)?.[1]
    const progressRule = styles.match(/\.progress \{([\s\S]*?)\n\}/)?.[1]
    const resultRule = styles.match(/\.result \{([\s\S]*?)\n\}/)?.[1]

    expect(sceneRule).toContain('width: min(720px, calc(100vw - 40px));')
    expect(sceneRule).not.toContain('perspective:')
    expect(bookRule).toContain('aspect-ratio: 3 / 2;')
    expect(leafStackRule).toContain('--binder-edge-width: 7px;')
    expect(leafStackRule).not.toContain('rotateX')
    expect(pagesRule).toContain('var(--binder-edge-width)')
    expect(slotGridRule).toContain('grid-template-rows: repeat(3, minmax(0, 1fr));')
    expect(slotGridRule).toContain('place-items: center;')
    expect(pageRule).toContain('--binder-page-inset: clamp(12px, 1.8vw, 18px);')
    expect(pageRule).toContain('--binder-page-gap: clamp(6px, 1vw, 9px);')
    expect(pageRule).toContain('--binder-page-footer-height: 26px;')
    expect(pageRule).toContain('padding: var(--binder-page-inset);')
    expect(leftPageRule).toContain('grid-template-rows: minmax(0, 1fr) auto;')
    expect(leftPageRule).toContain('gap: var(--binder-page-gap);')
    expect(rightPageRule).toContain('grid-template-rows: minmax(0, 1fr) auto;')
    expect(rightPageRule).toContain('gap: var(--binder-page-gap);')
    expect(progressRule).toContain('height: var(--binder-page-footer-height);')
    expect(resultRule).toContain('height: var(--binder-page-footer-height);')
    expect(resultRule).toContain('width: 100%;')
    expect(cardSlotRule).toContain('width: min(82%, 248px);')
    expect(cardSlotRule).toContain('max-height: 100%;')
    expect(cardSlotRule).toContain('place-self: center;')
    expect(coverInnerRule).toContain('transform: rotateY(180deg);')
    expect(coverInnerRule).not.toContain('translateZ')
    expect(coverFaceRule).toContain('var(--binder-edge-width)')
    expect(styles).not.toContain('.pageRule {')
    expect(narrowScreenRule).toContain('--binder-edge-width: 4px;')
    expect(narrowScreenRule).not.toContain('display: none;')
  })

  it('omits pagination on a single nine-pocket page', () => {
    render(
      <CollectionBinder
        event={binderEvent({ progress: { owned_copies: 6, unique_cards: 4, total_cards: 9 } })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(screen.queryByTestId('binder-page-indicator')).not.toBeInTheDocument()
    expect(screen.getByText('4 / 9')).toBeInTheDocument()
  })

  it('shows nine fixed catalog pockets and all historically owned cards on the current page', () => {
    const { container } = render(
      <CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />
    )

    expect(container.querySelectorAll('[data-slot-position]')).toHaveLength(9)
    expect(screen.getByTestId('binder-slot')).toHaveAttribute('data-catalog-number', '005')
    expect(screen.getByTestId('binder-slot-card')).toHaveAttribute('data-card-face', 'front')
    expect(screen.getByTestId('binder-slot-artwork-001')).toHaveAttribute(
      'src',
      '/images/collections/aespa/karina-01-r1.webp'
    )
    expect(screen.getByTestId('binder-slot-artwork-003')).toHaveAttribute(
      'src',
      '/images/collections/aespa/winter-01-r1.webp'
    )
    expect(screen.getByTestId('binder-slot-artwork-005')).toHaveAttribute(
      'src',
      COLLECTION.card.artwork.portrait_url
    )
    expect(screen.getByTestId('binder-slot-artwork-009')).toHaveAttribute(
      'src',
      '/images/collections/aespa/ningning-02-r1.webp'
    )
    expect(screen.queryByTestId('binder-slot-artwork-002')).not.toBeInTheDocument()
  })

  it('opens the nine-card page containing a draw beyond the first page', () => {
    const current = {
      ...COLLECTION.card,
      id: 21,
      key: 'rei-03',
      number: '011',
      name: 'Rei',
      artwork: {
        portrait_url: '/images/collections/ive/rei-03-r1.webp',
        square_url: null,
        backdrop_url: null,
      },
    }
    render(
      <CollectionBinder
        event={binderEvent({
          card: current,
          set: { id: 2, key: 'ive', name: 'IVE' },
          progress: { owned_copies: 2, unique_cards: 2, total_cards: 11 },
          owned_cards: [
            { ...COLLECTION.owned_cards[0], copy_count: 1 },
            { card: current, rarity: COLLECTION.rarity, copy_count: 1 },
          ],
        })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(screen.getByTestId('binder-page-indicator')).toHaveTextContent('2 / 2')
    expect(screen.getByTestId('binder-slot')).toHaveAttribute('data-slot-position', '11')
    expect(screen.getByTestId('binder-slot')).toHaveAttribute('data-catalog-number', '011')
    expect(screen.queryByTestId('binder-slot-artwork-001')).not.toBeInTheDocument()
    expect(screen.getByTestId('binder-slot-artwork-011')).toHaveAttribute(
      'src',
      current.artwork.portrait_url
    )
  })

  it('shows duplicate count on one pocket instead of occupying another pocket', () => {
    const ownedCards = COLLECTION.owned_cards.map(item =>
      item.card.id === COLLECTION.card.id ? { ...item, copy_count: 3 } : item
    )
    render(
      <CollectionBinder
        event={binderEvent({
          is_new: false,
          copy_count: 3,
          progress: { ...COLLECTION.progress, owned_copies: 8 },
          owned_cards: ownedCards,
        })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
        staticPreview
      />
    )

    expect(screen.getByTestId('binder-slot-copy-005')).toHaveTextContent('×3')
    expect(screen.getAllByTestId('binder-slot-artwork-005')).toHaveLength(1)
    expect(screen.getByTestId('binder-slot-card')).toHaveStyle({ opacity: '1' })
  })

  it('falls back to the selected card for a legacy event without inventory', () => {
    render(
      <CollectionBinder
        event={binderEvent({ owned_cards: undefined })}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
        staticPreview
      />
    )

    expect(screen.getByTestId('binder-slot')).toHaveAttribute('data-catalog-number', '005')
    expect(screen.getByTestId('binder-slot-artwork-005')).toHaveAttribute(
      'src',
      COLLECTION.card.artwork.portrait_url
    )
  })

  it('uses one 2:3 geometry for the revealed artwork and binder slots', () => {
    const styles = readFileSync(resolve(import.meta.dirname, 'CollectionBinder.module.css'), 'utf8')
    const miniSlotRule = styles.match(/\.miniSlot \{([\s\S]*?)\n\}/)?.[1]
    const cardSlotRule = styles.match(/\.cardSlot \{([\s\S]*?)\n\}/)?.[1]
    const cardOriginRule = styles.match(/\.cardOrigin \{([\s\S]*?)\n\}/)?.[1]
    const cardFaceRule = [...styles.matchAll(/\.cardFace \{([\s\S]*?)\n\}/g)]
      .map(match => match[1])
      .find(rule => rule.includes('box-sizing'))
    const artworkFrameRule = styles.match(/\.artworkFrame \{([\s\S]*?)\n\}/)?.[1]

    expect(miniSlotRule).toContain('aspect-ratio: 2 / 3;')
    expect(cardSlotRule).toContain('aspect-ratio: 2 / 3;')
    expect(cardSlotRule).toContain('border: 0;')
    expect(cardOriginRule).toContain('inset: 0;')
    expect(cardFaceRule).toContain('border: 0;')
    expect(artworkFrameRule).toContain('position: absolute;')
    expect(artworkFrameRule).toContain('inset: 0;')
    expect(styles.match(/\.cardBack \{([\s\S]*?)\n\}/)?.[1]).toContain(
      'transform: rotateY(180deg);'
    )
    expect(styles.match(/\.cardFront \{([\s\S]*?)\n\}/)?.[1]).toContain('transform: rotateY(0deg);')
  })

  it('keeps the revealed card aligned with its stage inside a scaled editor preview', async () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function () {
        switch (this.dataset.testid) {
          case 'binder-book':
            return domRect(74, 960, 396, 240)
          case 'binder-card-origin':
            return domRect(312, 990, 108, 162)
          case 'binder-slot-card':
            return domRect(101, 1018, 40, 60)
          default:
            return domRect(0, 0, 0, 0)
        }
      })
    const offsetWidthSpy = vi
      .spyOn(HTMLElement.prototype, 'offsetWidth', 'get')
      .mockImplementation(function () {
        return this.dataset.testid === 'binder-book' ? 660 : 0
      })
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      callback(0)
      return 1
    })

    try {
      render(
        <CollectionBinder
          event={binderEvent()}
          theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
          staticPreview
        />
      )

      await waitFor(() => {
        const card = screen.getByTestId('collection-card')
        expect(Number.parseFloat(card.style.left)).toBeCloseTo((312 - 74) / 0.6)
        expect(Number.parseFloat(card.style.top)).toBeCloseTo((990 - 960) / 0.6)
        expect(Number.parseFloat(card.style.width)).toBeCloseTo(180)
        expect(Number.parseFloat(card.style.height)).toBeCloseTo(270)
      })
    } finally {
      requestFrame.mockRestore()
      offsetWidthSpy.mockRestore()
      rectSpy.mockRestore()
    }
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
            collection: {
              ...COLLECTION,
              is_new: false,
              copy_count: 3,
              progress: { ...COLLECTION.progress, owned_copies: 8 },
              owned_cards: COLLECTION.owned_cards.map(item =>
                item.card.id === COLLECTION.card.id ? { ...item, copy_count: 3 } : item
              ),
            },
          },
        }}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(
      screen.getByRole('status', { name: 'Bob 的卡冊：獲得稀有卡月巡羅盤' })
    ).toBeInTheDocument()
    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-result', 'duplicate')
    expect(screen.getAllByText('×3')).toHaveLength(2)
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

  it('keeps missing artwork readable in the subtle sample preview', () => {
    const event = binderEvent({
      card: {
        ...COLLECTION.card,
        artwork: { portrait_url: null, square_url: null, backdrop_url: null },
      },
    })

    render(
      <CollectionBinder
        event={{
          ...event,
          actor_display_name: null,
          payload: { ...event.payload, preview: true },
        }}
        theme={{ ...DEFAULT_COMMUNITY_OVERLAY_THEME, motion: 'subtle' }}
        staticPreview
      />
    )

    expect(screen.getByRole('status', { name: '觀眾 的卡冊：獲得稀有卡月巡羅盤' })).toHaveAttribute(
      'data-motion',
      'subtle'
    )
    expect(screen.getByTestId('card-artwork')).toHaveAttribute('aria-label', '月巡羅盤圖片尚未提供')
    expect(screen.getByText('PREVIEW')).toBeInTheDocument()
  })

  it('uses the final readable state when the operating system requests reduced motion', () => {
    reducedMotion.value = true
    render(<CollectionBinder event={binderEvent()} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    expect(screen.getByTestId('collection-binder')).toHaveAttribute('data-motion-state', 'final')
  })
})
