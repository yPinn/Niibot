import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { AnimatePresence } from 'motion/react'

import {
  type CommunityOverlayEvent,
  type CommunityOverlayTheme,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  getCommunityOverlayFeed,
  getCommunityOverlayTheme,
} from '@/api/communityOverlay'
import { CheckinCard } from '@/components/community-overlay/CheckinCard'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'

import styles from './CommunityOverlay.module.css'

const POLL_INTERVAL_MS = 1_000
const THEME_POLL_INTERVAL_MS = 5_000

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

interface PlaybackState {
  active: CheckinEvent | null
  queue: CheckinEvent[]
}

type PlaybackAction = { type: 'enqueue'; events: CheckinEvent[] } | { type: 'advance' }

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

function ScopedCommunityOverlay({ publicKey, preview }: { publicKey: string; preview: boolean }) {
  const cursorRef = useRef<number | undefined>(preview ? 0 : undefined)
  const fetchingRef = useRef(false)
  const themeFetchingRef = useRef(false)
  const themeRevisionRef = useRef<number | null>(null)
  const seenIdsRef = useRef(new Set<number>())
  const [playback, dispatch] = useReducer(playbackReducer, { active: null, queue: [] })
  const [theme, setTheme] = useState<CommunityOverlayTheme>(DEFAULT_COMMUNITY_OVERLAY_THEME)

  const fetchTheme = useCallback(async () => {
    if (!publicKey || themeFetchingRef.current) return
    themeFetchingRef.current = true
    try {
      const published = await getCommunityOverlayTheme(publicKey)
      if (
        published.renderer === 'checkin-card' &&
        published.schema_version === 1 &&
        published.revision_id !== themeRevisionRef.current
      ) {
        themeRevisionRef.current = published.revision_id
        setTheme(published.theme)
      }
    } catch {
      // Keep the renderer usable and retry after transient API/network failures.
    } finally {
      themeFetchingRef.current = false
    }
  }, [publicKey])

  const fetchEvents = useCallback(async () => {
    if (!publicKey || fetchingRef.current) return
    fetchingRef.current = true
    try {
      const feed = await getCommunityOverlayFeed(publicKey, cursorRef.current)
      cursorRef.current = feed.cursor
      const incoming = feed.events.filter(isCheckinEvent).filter(event => {
        if (seenIdsRef.current.has(event.id)) return false
        seenIdsRef.current.add(event.id)
        return true
      })
      if (incoming.length) dispatch({ type: 'enqueue', events: incoming })
    } catch {
      // OBS sources stay transparent during transient API/network failures.
    } finally {
      fetchingRef.current = false
    }
  }, [publicKey])

  usePolling({
    fetchFn: fetchTheme,
    intervalMs: THEME_POLL_INTERVAL_MS,
    enabled: Boolean(publicKey),
  })

  usePolling({
    fetchFn: fetchEvents,
    intervalMs: POLL_INTERVAL_MS,
    enabled: Boolean(publicKey),
  })

  useEffect(() => {
    if (!playback.active) return
    const timeout = window.setTimeout(() => dispatch({ type: 'advance' }), theme.display_ms)
    return () => window.clearTimeout(timeout)
  }, [playback.active, theme.display_ms])

  return (
    <main className={styles.stage} data-placement={theme.placement} aria-live="polite">
      <AnimatePresence mode="wait">
        {playback.active && (
          <CheckinCard key={playback.active.id} event={playback.active} theme={theme} />
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

  useDocumentTitle('Community Overlay')

  return <ScopedCommunityOverlay key={scope} publicKey={publicKey} preview={preview} />
}
