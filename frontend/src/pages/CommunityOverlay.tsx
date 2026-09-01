import { useEffect, useReducer, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AnimatePresence } from 'motion/react'

import {
  type CommunityOverlayContentType,
  type CommunityOverlayEvent,
  type CommunityOverlayTheme,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
} from '@/api/communityOverlay'
import {
  type CommunityOverlayStreamMessage,
  openCommunityOverlayStream,
} from '@/api/communityOverlayStream'
import { CheckinCard } from '@/components/community-overlay/CheckinCard'
import { TarotCard } from '@/components/community-overlay/TarotCard'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import styles from './CommunityOverlay.module.css'

interface CheckinPayload extends Record<string, unknown> {
  total_days: number
  checkin_date: string
  preview?: boolean
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

type RenderableEvent = CheckinEvent | TarotEvent

interface PlaybackState {
  active: RenderableEvent | null
  queue: RenderableEvent[]
}

type PlaybackAction = { type: 'enqueue'; events: RenderableEvent[] } | { type: 'advance' }

function playbackReducer(state: PlaybackState, action: PlaybackAction): PlaybackState {
  if (action.type === 'enqueue') {
    if (action.events.length === 0) return state
    if (!state.active) {
      const [active, ...remaining] = action.events
      return { active, queue: [...state.queue, ...remaining] }
    }
    return { ...state, queue: [...state.queue, ...action.events] }
  }

  const [active = null, ...queue] = state.queue
  return { active, queue }
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

function blockTypeForEvent(event: RenderableEvent): CommunityOverlayContentType {
  return event.event_type === 'tarot.drawn' ? 'tarot' : 'checkin'
}

const RENDERERS: Record<CommunityOverlayContentType, string> = {
  checkin: 'checkin-card',
  tarot: 'tarot-card',
}

const STABLE_STREAM_MS = 30_000

function ScopedCommunityOverlay({ publicKey, preview }: { publicKey: string; preview: boolean }) {
  const themeRevisionRef = useRef<Record<CommunityOverlayContentType, number | null>>({
    checkin: null,
    tarot: null,
  })
  const seenIdsRef = useRef(new Set<number>())
  const [playback, dispatch] = useReducer(playbackReducer, { active: null, queue: [] })
  const [themes, setThemes] = useState<Record<CommunityOverlayContentType, CommunityOverlayTheme>>({
    checkin: DEFAULT_COMMUNITY_OVERLAY_THEME,
    tarot: DEFAULT_TAROT_OVERLAY_THEME,
  })

  useEffect(() => {
    if (!publicKey) return
    let active = true
    let cursor: number | undefined = preview ? 0 : undefined
    let attempt = 0
    let controller: AbortController | null = null
    let reconnectTimer: number | null = null

    const applyMessage = (message: CommunityOverlayStreamMessage) => {
      if (!active) return
      cursor = message.cursor
      for (const blockType of Object.keys(message.themes) as CommunityOverlayContentType[]) {
        const published = message.themes[blockType]
        if (
          !published ||
          published.renderer !== RENDERERS[blockType] ||
          published.schema_version !== 1 ||
          published.revision_id === themeRevisionRef.current[blockType]
        ) {
          continue
        }
        themeRevisionRef.current[blockType] = published.revision_id
        setThemes(current => ({ ...current, [blockType]: published.theme }))
      }
      const incoming = message.events
        .filter((event): event is RenderableEvent => isCheckinEvent(event) || isTarotEvent(event))
        .filter(event => {
          if (seenIdsRef.current.has(event.id)) return false
          seenIdsRef.current.add(event.id)
          if (seenIdsRef.current.size > 1_000) {
            seenIdsRef.current.delete(seenIdsRef.current.values().next().value as number)
          }
          return true
        })
      if (incoming.length) dispatch({ type: 'enqueue', events: incoming })
    }

    const connect = () => {
      controller = new AbortController()
      const connectedAt = Date.now()
      void openCommunityOverlayStream({
        publicKey,
        afterId: cursor,
        signal: controller.signal,
        onMessage: applyMessage,
      })
        .catch(() => undefined)
        .finally(() => {
          if (!active || controller?.signal.aborted) return
          if (Date.now() - connectedAt >= STABLE_STREAM_MS) attempt = 0
          const base = Math.min(1_000 * 2 ** attempt, 30_000)
          const delay = Math.round(base * (0.8 + Math.random() * 0.4))
          attempt += 1
          reconnectTimer = window.setTimeout(connect, delay)
        })
    }

    connect()
    return () => {
      active = false
      controller?.abort()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    }
  }, [preview, publicKey])

  const activeBlockType = playback.active ? blockTypeForEvent(playback.active) : 'checkin'
  const activeTheme = themes[activeBlockType]

  useEffect(() => {
    if (!playback.active) return
    const timeout = window.setTimeout(() => dispatch({ type: 'advance' }), activeTheme.display_ms)
    return () => window.clearTimeout(timeout)
  }, [activeTheme.display_ms, playback.active])

  return (
    <main className={styles.stage} data-placement={activeTheme.placement} aria-live="polite">
      <AnimatePresence mode="wait">
        {playback.active?.event_type === 'checkin.recorded' && (
          <CheckinCard key={playback.active.id} event={playback.active} theme={activeTheme} />
        )}
        {playback.active?.event_type === 'tarot.drawn' && (
          <TarotCard key={playback.active.id} event={playback.active} theme={activeTheme} />
        )}
      </AnimatePresence>
    </main>
  )
}

export default function CommunityOverlay() {
  const location = useLocation()
  const overlayParams = new URLSearchParams(location.hash.replace(/^#/, ''))
  const publicKey = overlayParams.get('key')?.trim() || ''
  const preview = overlayParams.get('preview') === '1'
  const scope = `${publicKey}:${preview ? 'preview' : 'live'}`

  useDocumentTitle('Live Display')

  return <ScopedCommunityOverlay key={scope} publicKey={publicKey} preview={preview} />
}
