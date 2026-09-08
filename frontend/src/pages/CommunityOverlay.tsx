import { useEffect, useReducer, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AnimatePresence } from 'motion/react'

import {
  type CommunityOverlayContentType,
  type CommunityOverlayTheme,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
} from '@/api/communityOverlay'
import {
  type CommunityOverlayStreamMessage,
  openCommunityOverlayStream,
} from '@/api/communityOverlayStream'
import { getOverlayPlaybackLifetimeMs } from '@/components/community-overlay/collectionBinderMotion'
import { buildCommunityOverlayPreviewEvent } from '@/components/community-overlay/previewFixtures'
import {
  OverlayEventRenderer,
  type ResolvedOverlayEvent,
  resolveOverlayEvent,
  supportsPublishedRenderer,
} from '@/components/community-overlay/rendererRegistry'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import styles from './CommunityOverlay.module.css'

interface PlaybackItem {
  resolved: ResolvedOverlayEvent
  theme: CommunityOverlayTheme
}

interface PlaybackState {
  active: PlaybackItem | null
  queue: PlaybackItem[]
  stageTheme: CommunityOverlayTheme | null
  exiting: boolean
}

type PlaybackAction =
  | { type: 'enqueue'; items: PlaybackItem[]; now: number }
  | { type: 'beginExit' }
  | { type: 'exitComplete'; now: number }

function isPlayableAt(item: PlaybackItem, now: number): boolean {
  const { expires_at: expiresAt } = item.resolved.event
  if (expiresAt === null) return true
  const expiresAtMs = Date.parse(expiresAt)
  return Number.isFinite(expiresAtMs) && expiresAtMs > now
}

function promoteNext(
  queue: PlaybackItem[],
  now: number,
  stageTheme: CommunityOverlayTheme | null
): PlaybackState {
  const nextIndex = queue.findIndex(item => isPlayableAt(item, now))
  if (nextIndex < 0) return { active: null, queue: [], stageTheme, exiting: false }
  const active = queue[nextIndex]
  return {
    active,
    queue: queue.slice(nextIndex + 1),
    stageTheme: active.theme,
    exiting: false,
  }
}

function playbackReducer(state: PlaybackState, action: PlaybackAction): PlaybackState {
  if (action.type === 'enqueue') {
    if (action.items.length === 0) return state
    if (!state.active && !state.exiting) {
      return promoteNext([...state.queue, ...action.items], action.now, state.stageTheme)
    }
    return { ...state, queue: [...state.queue, ...action.items] }
  }

  if (action.type === 'beginExit') {
    if (!state.active) return state
    return { ...state, active: null, exiting: true }
  }

  if (!state.exiting) return state
  return promoteNext(state.queue, action.now, state.stageTheme)
}

const STABLE_STREAM_MS = 30_000

interface ScopedCommunityOverlayProps {
  publicKey: string
  preview: boolean
  blockFilter?: CommunityOverlayContentType
  developmentSample?: CommunityOverlayContentType
}

function ScopedCommunityOverlay({
  publicKey,
  preview,
  blockFilter,
  developmentSample,
}: ScopedCommunityOverlayProps) {
  const themeRevisionRef = useRef<Record<CommunityOverlayContentType, number | null>>({
    checkin: null,
    tarot: null,
  })
  const seenIdsRef = useRef(new Set<number>())
  const [playback, dispatch] = useReducer(playbackReducer, {
    active: null,
    queue: [],
    stageTheme: null,
    exiting: false,
  })
  const [themes, setThemes] = useState<Record<CommunityOverlayContentType, CommunityOverlayTheme>>({
    checkin: DEFAULT_COMMUNITY_OVERLAY_THEME,
    tarot: DEFAULT_TAROT_OVERLAY_THEME,
  })
  const themesRef = useRef(themes)

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
      let nextThemes = themesRef.current
      for (const blockType of Object.keys(message.themes)) {
        if (blockType !== 'checkin' && blockType !== 'tarot') continue
        const published = message.themes[blockType]
        if (
          !published ||
          !supportsPublishedRenderer(blockType, published.renderer, published.schema_version) ||
          published.revision_id === themeRevisionRef.current[blockType]
        ) {
          continue
        }
        themeRevisionRef.current[blockType] = published.revision_id
        nextThemes = { ...nextThemes, [blockType]: published.theme }
      }
      if (nextThemes !== themesRef.current) {
        themesRef.current = nextThemes
        setThemes(nextThemes)
      }
      const now = Date.now()
      const incoming = message.events
        .map(resolveOverlayEvent)
        .filter((event): event is ResolvedOverlayEvent => event !== null)
        .filter(event => !blockFilter || event.blockType === blockFilter)
        .filter(event => isPlayableAt({ resolved: event, theme: nextThemes[event.blockType] }, now))
        .filter(event => {
          if (seenIdsRef.current.has(event.event.id)) return false
          seenIdsRef.current.add(event.event.id)
          if (seenIdsRef.current.size > 1_000) {
            seenIdsRef.current.delete(seenIdsRef.current.values().next().value as number)
          }
          return true
        })
        .map(resolved => ({ resolved, theme: nextThemes[resolved.blockType] }))
      if (incoming.length) dispatch({ type: 'enqueue', items: incoming, now })
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

    if (developmentSample) {
      const sampleEvent = buildCommunityOverlayPreviewEvent(developmentSample)
      applyMessage({
        type: 'snapshot',
        cursor: sampleEvent.id,
        events: [sampleEvent],
        themes: {},
      })
    } else {
      connect()
    }
    return () => {
      active = false
      controller?.abort()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    }
  }, [preview, publicKey, blockFilter, developmentSample])

  const activeTheme = playback.stageTheme ?? themes.checkin

  useEffect(() => {
    if (!playback.active) return
    const playbackDurationMs = getOverlayPlaybackLifetimeMs(
      playback.active.resolved.rendererId,
      playback.active.theme.display_ms
    )
    const timeout = window.setTimeout(() => dispatch({ type: 'beginExit' }), playbackDurationMs)
    return () => window.clearTimeout(timeout)
  }, [playback.active])

  return (
    <main className={styles.stage} data-placement={activeTheme.placement} aria-live="polite">
      <AnimatePresence
        mode="wait"
        onExitComplete={() => dispatch({ type: 'exitComplete', now: Date.now() })}
      >
        {playback.active && (
          <OverlayEventRenderer
            key={playback.active.resolved.event.id}
            resolved={playback.active.resolved}
            theme={playback.active.theme}
          />
        )}
      </AnimatePresence>
    </main>
  )
}

function parseBlockFilter(value: string | null): CommunityOverlayContentType | undefined {
  return value === 'checkin' || value === 'tarot' ? value : undefined
}

export default function CommunityOverlay() {
  const location = useLocation()
  const overlayParams = new URLSearchParams(location.hash.replace(/^#/, ''))
  const publicKey = overlayParams.get('key')?.trim() || ''
  const preview = overlayParams.get('preview') === '1'
  const blockFilter = parseBlockFilter(overlayParams.get('block'))
  const developmentSample =
    import.meta.env.DEV && preview ? parseBlockFilter(overlayParams.get('sample')) : undefined
  const scope = `${publicKey}:${preview ? 'preview' : 'live'}:${blockFilter ?? 'all'}:${developmentSample ?? 'stream'}`

  useDocumentTitle('Live Display')

  return (
    <ScopedCommunityOverlay
      key={scope}
      publicKey={publicKey}
      preview={preview}
      blockFilter={blockFilter}
      developmentSample={developmentSample}
    />
  )
}
