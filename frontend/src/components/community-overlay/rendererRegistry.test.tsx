import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEFAULT_COMMUNITY_OVERLAY_THEME } from '@/api/communityOverlay'

import {
  OverlayEventRenderer,
  resolveOverlayEvent,
  supportsPublishedRenderer,
} from './rendererRegistry'

const BASE_EVENT = {
  id: 1,
  event_type: 'checkin.recorded',
  schema_version: 1,
  source: 'twitch',
  actor_display_name: 'Alice',
  occurred_at: '2099-09-08T10:00:00Z',
  expires_at: '2099-09-08T10:10:00Z',
}

const COLLECTION = {
  draw_id: 17,
  pool_revision_id: 3,
  algorithm_version: 'weighted-rarity-v1',
  card: {
    id: 11,
    revision_id: 2,
    key: 'moonlit-compass',
    number: '011',
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

const COMPLETE_COLLECTION = {
  ...COLLECTION,
  is_new: false,
  copy_count: 2,
  progress: { owned_copies: 3, unique_cards: 2, total_cards: 24 },
  owned_cards: [
    {
      card: COLLECTION.card,
      rarity: COLLECTION.rarity,
      copy_count: 2,
    },
    {
      card: {
        ...COLLECTION.card,
        id: 12,
        revision_id: 3,
        key: 'starlit-map',
        number: '012',
        name: '星圖',
      },
      rarity: { key: 'common', label: '普通', rank: 1, effect_intensity: 10 },
      copy_count: 1,
    },
  ],
}

function checkinEvent(collection: unknown = undefined) {
  return {
    ...BASE_EVENT,
    payload: {
      total_days: 8,
      checkin_date: '2099-09-08',
      ...(collection === undefined ? {} : { collection }),
    },
  }
}

describe('community overlay renderer registry', () => {
  it('keeps a v1 check-in without collection data on the legacy ticket renderer', () => {
    const resolved = resolveOverlayEvent(checkinEvent())
    expect(resolved?.rendererId).toBe('checkin-card')

    render(<OverlayEventRenderer resolved={resolved!} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)
    expect(screen.getByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
  })

  it('keeps legacy v1 collection events without inventory on the binder', () => {
    const resolved = resolveOverlayEvent(checkinEvent(COLLECTION))
    expect(resolved?.rendererId).toBe('collection-binder')

    render(<OverlayEventRenderer resolved={resolved!} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)
    expect(screen.getByLabelText('Alice 的卡冊：獲得稀有卡月巡羅盤')).toBeInTheDocument()
  })

  it('uses the binder when the complete owned-card inventory validates', () => {
    expect(resolveOverlayEvent(checkinEvent(COMPLETE_COLLECTION))?.rendererId).toBe(
      'collection-binder'
    )
  })

  it.each([
    {
      ...COMPLETE_COLLECTION,
      owned_cards: [COMPLETE_COLLECTION.owned_cards[0], COMPLETE_COLLECTION.owned_cards[0]],
    },
    {
      ...COMPLETE_COLLECTION,
      owned_cards: COMPLETE_COLLECTION.owned_cards.map((item, index) =>
        index === 0 ? { ...item, copy_count: 3 } : item
      ),
    },
    {
      ...COMPLETE_COLLECTION,
      owned_cards: [COMPLETE_COLLECTION.owned_cards[1]],
    },
  ])('falls back when the complete inventory is inconsistent', collection => {
    expect(resolveOverlayEvent(checkinEvent(collection))?.rendererId).toBe('checkin-card')
  })

  it.each([
    null,
    { ...COLLECTION, copy_count: 0 },
    { ...COLLECTION, algorithm_version: 'Weighted V1' },
    { ...COLLECTION, progress: { owned_copies: 1, unique_cards: 3, total_cards: 2 } },
    { ...COLLECTION, card: { ...COLLECTION.card, artwork: { portrait_url: 42 } } },
  ])('safely falls back to the legacy ticket for malformed collection data', collection => {
    const resolved = resolveOverlayEvent(checkinEvent(collection))
    expect(resolved?.rendererId).toBe('checkin-card')
  })

  it.each([
    { ...COLLECTION, is_new: false, copy_count: 1 },
    { ...COLLECTION, is_new: true, copy_count: 2 },
    { ...COLLECTION, progress: { owned_copies: 2, unique_cards: 3, total_cards: 8 } },
    { ...COLLECTION, progress: { owned_copies: 8, unique_cards: 9, total_cards: 8 } },
    { ...COLLECTION, copy_count: 9, progress: { ...COLLECTION.progress, owned_copies: 8 } },
    {
      ...COLLECTION,
      is_new: false,
      copy_count: 2,
      progress: { owned_copies: 8, unique_cards: 8, total_cards: 24 },
    },
  ])('falls back when collection counters are semantically inconsistent', collection => {
    expect(resolveOverlayEvent(checkinEvent(collection))?.rendererId).toBe('checkin-card')
  })

  it('rejects unsupported event versions while retaining registered theme renderers', () => {
    expect(resolveOverlayEvent({ ...checkinEvent(), schema_version: 2 })).toBeNull()
    expect(supportsPublishedRenderer('checkin', 'checkin-card', 1)).toBe(true)
    expect(supportsPublishedRenderer('tarot', 'tarot-card', 1)).toBe(true)
    expect(supportsPublishedRenderer('checkin', 'tenant-html', 1)).toBe(false)
  })
})
