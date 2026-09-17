import { useCallback, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { getPublicQueueState, type PublicQueueState, type QueueEntry } from '@/api/gameQueue'
import { OverlayReconnectingBadge } from '@/components/OverlayReconnectingBadge'
import { OVERLAY_POLL_INTERVAL_MS } from '@/config/overlayPolling'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'
import { reportSilent } from '@/lib/clientErrorReporter'

import styles from './GameQueueOverlay.module.css'

function PlayerSection({ entries, label }: { entries: QueueEntry[]; label: string }) {
  if (entries.length === 0) return null
  return (
    <div className={styles.section}>
      <div className={styles.sectionLabel}>{label}</div>
      {entries.map(entry => (
        <div key={entry.id} className={styles.entry}>
          <span className={styles.position}>{entry.position}</span>
          <span className={styles.name}>{entry.user_name}</span>
        </div>
      ))}
    </div>
  )
}

export default function GameQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const [searchParams] = useSearchParams()
  const isPreview = searchParams.get('preview') === '1'
  const [state, setState] = useState<PublicQueueState | null>(null)
  // 2+ consecutive poll failures before showing the reconnecting badge —
  // avoids flickering it on a single dropped request.
  const consecutiveFailuresRef = useRef(0)
  const [isStale, setIsStale] = useState(false)

  useDocumentTitle('Game Queue Overlay')

  const fetchState = useCallback(async () => {
    if (!username) return
    try {
      const data = await getPublicQueueState(username)
      setState(data)
      consecutiveFailuresRef.current = 0
      setIsStale(false)
    } catch (e) {
      consecutiveFailuresRef.current += 1
      if (consecutiveFailuresRef.current >= 2) setIsStale(true)
      reportSilent(e)
    }
  }, [username])

  usePolling({
    fetchFn: fetchState,
    intervalMs: OVERLAY_POLL_INTERVAL_MS.gameQueue,
    enabled: !!username,
  })

  if (!username) return null

  if (!state || (state.current_batch.length === 0 && state.next_batch.length === 0)) {
    return isPreview ? (
      <div className={styles.previewEmpty}>
        <OverlayReconnectingBadge visible={isStale} />
      </div>
    ) : null
  }

  const remaining = state.total_active - state.current_batch.length - state.next_batch.length

  const panel = (
    <div className={styles.panel}>
      <PlayerSection entries={state.current_batch} label="現在上場" />
      <PlayerSection entries={state.next_batch} label="下一批" />
      {remaining > 0 && <div className={styles.remaining}>+{remaining} 人排隊中</div>}
    </div>
  )

  if (isPreview) {
    return (
      <div className={styles.previewWrapper}>
        <OverlayReconnectingBadge visible={isStale} />
        {panel}
      </div>
    )
  }

  return panel
}
