import type {
  CheckinCollectionSnapshot,
  CommunityOverlayEvent,
  CommunityOverlayTheme,
} from '@/api/communityOverlay'

import { CheckinCard } from './CheckinCard'
import { CollectionBinder } from './CollectionBinder'
import { TarotCard } from './TarotCard'

interface CheckinPayload extends Record<string, unknown> {
  total_days: number
  checkin_date: string
  preview?: boolean
  collection?: unknown
}

interface CheckinEvent extends CommunityOverlayEvent {
  event_type: 'checkin.recorded'
  schema_version: 1
  payload: CheckinPayload
}

interface TarotPayload extends Record<string, unknown> {
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

interface TarotEvent extends CommunityOverlayEvent {
  event_type: 'tarot.drawn'
  schema_version: 1
  payload: TarotPayload
}

interface LegacyCheckinResolvedEvent {
  rendererId: 'checkin-card'
  blockType: 'checkin'
  event: CheckinEvent
}

interface CollectionBinderResolvedEvent {
  rendererId: 'collection-binder'
  blockType: 'checkin'
  event: CheckinEvent & {
    payload: CheckinPayload & { collection: CheckinCollectionSnapshot }
  }
}

interface TarotResolvedEvent {
  rendererId: 'tarot-card'
  blockType: 'tarot'
  event: TarotEvent
}

export type ResolvedOverlayEvent =
  LegacyCheckinResolvedEvent | CollectionBinderResolvedEvent | TarotResolvedEvent

const KEY = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function isIntegerBetween(value: unknown, min: number, max = Number.MAX_SAFE_INTEGER) {
  return Number.isInteger(value) && Number(value) >= min && Number(value) <= max
}

function isSizedString(value: unknown, max: number, pattern?: RegExp): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= max &&
    (!pattern || pattern.test(value))
  )
}

function isNullableSizedString(value: unknown, max: number): value is string | null {
  return value === null || (typeof value === 'string' && value.length > 0 && value.length <= max)
}

export function parseCheckinCollectionSnapshot(value: unknown): CheckinCollectionSnapshot | null {
  if (!isRecord(value)) return null
  const card = value.card
  const set = value.set
  const rarity = value.rarity
  const progress = value.progress
  if (!isRecord(card) || !isRecord(set) || !isRecord(rarity) || !isRecord(progress)) return null
  const artwork = card.artwork
  if (!isRecord(artwork)) return null

  if (
    !isIntegerBetween(value.draw_id, 1) ||
    !isIntegerBetween(value.pool_revision_id, 1) ||
    !isSizedString(value.algorithm_version, 64, KEY) ||
    !isIntegerBetween(card.id, 1) ||
    !isIntegerBetween(card.revision_id, 1) ||
    !isSizedString(card.key, 64, KEY) ||
    !isSizedString(card.number, 16) ||
    !isSizedString(card.name, 100) ||
    !isNullableSizedString(artwork.portrait_url, 500) ||
    !isNullableSizedString(artwork.square_url, 500) ||
    !isNullableSizedString(artwork.backdrop_url, 500) ||
    !isIntegerBetween(set.id, 1) ||
    !isSizedString(set.key, 64, KEY) ||
    !isSizedString(set.name, 100) ||
    !isSizedString(rarity.key, 64, KEY) ||
    !isSizedString(rarity.label, 40) ||
    !isIntegerBetween(rarity.rank, 1, 32_767) ||
    !isIntegerBetween(rarity.effect_intensity, 0, 100) ||
    typeof value.is_new !== 'boolean' ||
    !isIntegerBetween(value.copy_count, 1) ||
    !isIntegerBetween(progress.owned_copies, 1) ||
    !isIntegerBetween(progress.unique_cards, 1) ||
    !isIntegerBetween(progress.total_cards, 1) ||
    value.is_new !== (Number(value.copy_count) === 1) ||
    Number(progress.unique_cards) > Number(progress.total_cards) ||
    Number(progress.owned_copies) < Number(progress.unique_cards) ||
    Number(progress.owned_copies) < Number(value.copy_count) ||
    Number(progress.unique_cards) > Number(progress.owned_copies) - Number(value.copy_count) + 1
  ) {
    return null
  }

  if ('owned_cards' in value) {
    const ownedCards = value.owned_cards
    if (!Array.isArray(ownedCards) || ownedCards.length === 0) return null

    const seenIds = new Set<number>()
    const seenNumbers = new Set<string>()
    let inventoryCopies = 0
    let selectedItem: Record<string, unknown> | null = null
    for (const item of ownedCards) {
      if (!isRecord(item) || !isRecord(item.card) || !isRecord(item.rarity)) return null
      const itemCard = item.card
      const itemArtwork = itemCard.artwork
      const itemRarity = item.rarity
      if (
        !isRecord(itemArtwork) ||
        !isIntegerBetween(itemCard.id, 1) ||
        !isIntegerBetween(itemCard.revision_id, 1) ||
        !isSizedString(itemCard.key, 64, KEY) ||
        !isSizedString(itemCard.number, 16) ||
        !isSizedString(itemCard.name, 100) ||
        !isNullableSizedString(itemArtwork.portrait_url, 500) ||
        !isNullableSizedString(itemArtwork.square_url, 500) ||
        !isNullableSizedString(itemArtwork.backdrop_url, 500) ||
        !isSizedString(itemRarity.key, 64, KEY) ||
        !isSizedString(itemRarity.label, 40) ||
        !isIntegerBetween(itemRarity.rank, 1, 32_767) ||
        !isIntegerBetween(itemRarity.effect_intensity, 0, 100) ||
        !isIntegerBetween(item.copy_count, 1)
      ) {
        return null
      }

      const itemId = Number(itemCard.id)
      const itemNumber = String(itemCard.number)
      if (seenIds.has(itemId) || seenNumbers.has(itemNumber)) return null
      seenIds.add(itemId)
      seenNumbers.add(itemNumber)
      inventoryCopies += Number(item.copy_count)
      if (itemId === Number(card.id)) selectedItem = item
    }

    if (
      ownedCards.length !== Number(progress.unique_cards) ||
      inventoryCopies !== Number(progress.owned_copies) ||
      !selectedItem ||
      Number(selectedItem.copy_count) !== Number(value.copy_count) ||
      !sameCollectionCard(selectedItem.card, card) ||
      !sameCollectionRarity(selectedItem.rarity, rarity)
    ) {
      return null
    }
  }

  return value as unknown as CheckinCollectionSnapshot
}

function sameCollectionCard(leftValue: unknown, rightValue: Record<string, unknown>): boolean {
  if (!isRecord(leftValue) || !isRecord(leftValue.artwork) || !isRecord(rightValue.artwork)) {
    return false
  }
  const leftArtwork = leftValue.artwork
  const rightArtwork = rightValue.artwork
  return (
    leftValue.id === rightValue.id &&
    leftValue.revision_id === rightValue.revision_id &&
    leftValue.key === rightValue.key &&
    leftValue.number === rightValue.number &&
    leftValue.name === rightValue.name &&
    leftArtwork.portrait_url === rightArtwork.portrait_url &&
    leftArtwork.square_url === rightArtwork.square_url &&
    leftArtwork.backdrop_url === rightArtwork.backdrop_url
  )
}

function sameCollectionRarity(leftValue: unknown, rightValue: Record<string, unknown>): boolean {
  return (
    isRecord(leftValue) &&
    leftValue.key === rightValue.key &&
    leftValue.label === rightValue.label &&
    leftValue.rank === rightValue.rank &&
    leftValue.effect_intensity === rightValue.effect_intensity
  )
}

function isCheckinEvent(event: CommunityOverlayEvent): event is CheckinEvent {
  return (
    event.event_type === 'checkin.recorded' &&
    event.schema_version === 1 &&
    Number.isInteger(event.payload.total_days) &&
    Number(event.payload.total_days) > 0 &&
    typeof event.payload.checkin_date === 'string'
  )
}

function isTarotEvent(event: CommunityOverlayEvent): event is TarotEvent {
  const { payload } = event
  return (
    event.event_type === 'tarot.drawn' &&
    event.schema_version === 1 &&
    typeof payload.card_id === 'string' &&
    typeof payload.card_name === 'string' &&
    typeof payload.card_name_en === 'string' &&
    (payload.orientation === 'upright' || payload.orientation === 'reversed') &&
    typeof payload.orientation_label === 'string' &&
    typeof payload.category === 'string' &&
    typeof payload.category_label === 'string' &&
    Array.isArray(payload.keywords) &&
    payload.keywords.every(keyword => typeof keyword === 'string') &&
    typeof payload.meaning === 'string' &&
    typeof payload.advice === 'string' &&
    typeof payload.image_path === 'string' &&
    payload.image_path.startsWith('/images/tarot/decks/') &&
    typeof payload.deck_id === 'string' &&
    Number.isInteger(payload.deck_version) &&
    Number(payload.deck_version) > 0
  )
}

export const COMMUNITY_OVERLAY_RENDERER_REGISTRY = {
  checkin: { publishedRenderer: 'checkin-card', schemaVersion: 1 },
  tarot: { publishedRenderer: 'tarot-card', schemaVersion: 1 },
} as const

export function supportsPublishedRenderer(
  blockType: string,
  renderer: string,
  schemaVersion: number
) {
  const registered =
    COMMUNITY_OVERLAY_RENDERER_REGISTRY[
      blockType as keyof typeof COMMUNITY_OVERLAY_RENDERER_REGISTRY
    ]
  if (!registered) return false
  return renderer === registered.publishedRenderer && schemaVersion === registered.schemaVersion
}

export function resolveOverlayEvent(event: CommunityOverlayEvent): ResolvedOverlayEvent | null {
  if (isCheckinEvent(event)) {
    const collection = parseCheckinCollectionSnapshot(event.payload.collection)
    if (!collection) return { rendererId: 'checkin-card', blockType: 'checkin', event }
    return {
      rendererId: 'collection-binder',
      blockType: 'checkin',
      event: { ...event, payload: { ...event.payload, collection } },
    }
  }
  if (isTarotEvent(event)) return { rendererId: 'tarot-card', blockType: 'tarot', event }
  return null
}

export function OverlayEventRenderer({
  resolved,
  theme,
}: {
  resolved: ResolvedOverlayEvent
  theme: CommunityOverlayTheme
}) {
  if (resolved.rendererId === 'collection-binder') {
    return <CollectionBinder event={resolved.event} theme={theme} />
  }
  if (resolved.rendererId === 'tarot-card') {
    return <TarotCard event={resolved.event} theme={theme} />
  }
  return <CheckinCard event={resolved.event} theme={theme} />
}
