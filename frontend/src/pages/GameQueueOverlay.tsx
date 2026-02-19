import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getPublicQueueState, type PublicQueueState, type QueueEntry } from '@/api/gameQueue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const POLL_INTERVAL = 10_000

function PlayerList({ entries, label }: { entries: QueueEntry[]; label: string }) {
  if (entries.length === 0) return null
  return (
    <div className="mb-6">
      <h2 className="mb-2 text-lg font-bold text-white/60">{label}</h2>
      <ul className="space-y-1">
        {entries.map(entry => (
          <li
            key={entry.id}
            className="flex items-center gap-3 rounded-md bg-white/10 px-4 py-2 text-xl font-semibold text-white"
          >
            <span className="text-base text-white/50">#{entry.position}</span>
            <span>{entry.user_name}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function GameQueueOverlay() {
  const { channelId } = useParams<{ channelId: string }>()
  const [state, setState] = useState<PublicQueueState | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useDocumentTitle('Game Queue Overlay')

  useEffect(() => {
    if (!channelId) return

    const fetchState = async () => {
      try {
        const data = await getPublicQueueState(channelId)
        setState(data)
      } catch {
        // silent on poll errors
      }
    }

    fetchState()
    pollRef.current = setInterval(fetchState, POLL_INTERVAL)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [channelId])

  if (!channelId) return null

  const isEmpty = !state || (state.current_batch.length === 0 && state.next_batch.length === 0)

  return (
    <div className="min-h-screen bg-transparent p-6 font-sans">
      {isEmpty ? (
        <p className="text-center text-lg text-white/40">-- 無排隊 --</p>
      ) : (
        <>
          <PlayerList entries={state!.current_batch} label="現在上場" />
          <PlayerList entries={state!.next_batch} label="下一批" />
          {state!.total_active > state!.current_batch.length + state!.next_batch.length && (
            <p className="text-center text-sm text-white/30">
              還有 {state!.total_active - state!.current_batch.length - state!.next_batch.length}{' '}
              人排隊中
            </p>
          )}
        </>
      )}
    </div>
  )
}
