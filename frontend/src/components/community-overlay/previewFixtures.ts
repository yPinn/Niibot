import type { CommunityOverlayContentType, CommunityOverlayEvent } from '@/api/communityOverlay'

import type { CollectionBinderEvent } from './CollectionBinder'
import type { TarotCardEvent } from './TarotCard'

const SAMPLE_COLLECTION_RARITY = {
  key: 'common',
  label: '普通',
  rank: 1,
  effect_intensity: 10,
}

const SAMPLE_OWNED_CARDS = [
  ['karina-01', 'Karina', 1],
  ['karina-02', 'Karina', 2],
  ['karina-03', 'Karina', 2],
  ['karina-04', 'Karina', 1],
  ['karina-05', 'Karina', 1],
  ['winter-01', 'Winter', 1],
].map(([key, name, copyCount], index) => ({
  card: {
    id: index + 1,
    revision_id: index + 1,
    key: String(key),
    number: String(index + 1).padStart(3, '0'),
    name: String(name),
    artwork: {
      portrait_url: `/images/collections/aespa/${key}-r1.webp`,
      square_url: null,
      backdrop_url: null,
    },
  },
  rarity: SAMPLE_COLLECTION_RARITY,
  copy_count: Number(copyCount),
}))

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
        key: 'karina-01',
        number: '001',
        name: 'Karina',
        artwork: {
          portrait_url: '/images/collections/aespa/karina-01-r1.webp',
          square_url: null,
          backdrop_url: null,
        },
      },
      set: { id: 1, key: 'aespa', name: 'aespa' },
      rarity: SAMPLE_COLLECTION_RARITY,
      is_new: true,
      copy_count: 1,
      progress: { owned_copies: 8, unique_cards: 6, total_cards: 9 },
      owned_cards: SAMPLE_OWNED_CARDS,
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
