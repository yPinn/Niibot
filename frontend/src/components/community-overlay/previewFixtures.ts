import type { CommunityOverlayContentType, CommunityOverlayEvent } from '@/api/communityOverlay'

import type { CollectionBinderEvent } from './CollectionBinder'
import type { TarotCardEvent } from './TarotCard'

export const SAMPLE_COLLECTION_BINDER_EVENT: CollectionBinderEvent = {
  actor_display_name: 'NiibotFan',
  payload: {
    total_days: 8,
    checkin_date: '2026-08-31',
    collection: {
      draw_id: 8,
      pool_revision_id: 1,
      algorithm_version: 'weighted-rarity-v1',
      card: {
        id: 1,
        revision_id: 1,
        key: 'astral-compass',
        number: 'FP-001',
        name: '星路羅盤',
        artwork: {
          portrait_url: null,
          square_url: null,
          backdrop_url: null,
        },
      },
      set: { id: 1, key: 'first-path', name: '初始航路' },
      rarity: { key: 'common', label: '普通', rank: 1, effect_intensity: 10 },
      is_new: true,
      copy_count: 1,
      progress: { owned_copies: 8, unique_cards: 6, total_cards: 24 },
    },
  },
}

export const SAMPLE_TAROT_CARD_EVENT: TarotCardEvent = {
  actor_display_name: 'NiibotFan',
  payload: {
    card_id: '0',
    card_name: '愚者',
    card_name_en: 'The Fool',
    orientation: 'upright',
    orientation_label: '正位',
    category: 'general',
    category_label: '綜合',
    keywords: ['新開始', '冒險', '自由'],
    meaning: '進入全新階段，無限可能正在展開。',
    advice: '保持開放心態，先踏出真誠的一步。',
    image_path: '/images/tarot/decks/rider-waite-smith-pkt/v1/cards/major-00-the-fool.jpg',
    deck_id: 'rider-waite-smith-pkt',
    deck_version: 1,
  },
}

const SAMPLE_EVENT_IDS: Record<CommunityOverlayContentType, number> = {
  checkin: 9_000_000_001,
  tarot: 9_000_000_002,
}

export function buildCommunityOverlayPreviewEvent(
  contentType: CommunityOverlayContentType,
  now = Date.now()
): CommunityOverlayEvent {
  const sample =
    contentType === 'checkin' ? SAMPLE_COLLECTION_BINDER_EVENT : SAMPLE_TAROT_CARD_EVENT
  return {
    id: SAMPLE_EVENT_IDS[contentType],
    event_type: contentType === 'checkin' ? 'checkin.recorded' : 'tarot.drawn',
    schema_version: 1,
    source: 'system',
    actor_display_name: sample.actor_display_name,
    payload: { ...sample.payload, preview: true },
    occurred_at: new Date(now).toISOString(),
    expires_at: new Date(now + 10 * 60_000).toISOString(),
  }
}
