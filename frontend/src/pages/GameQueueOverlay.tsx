import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getPublicQueueState, type PublicQueueState, type QueueEntry } from '@/api/gameQueue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const POLL_INTERVAL = 10_000

function PlayerList({ entries, label }: { entries: QueueEntry[]; label: string }) {
  if (entries.length === 0) return null
  return (
    <div className="mb-3">
      <div className="mb-1 text-xs font-bold uppercase tracking-widest text-white/50">{label}</div>
      {entries.map(entry => (
        <div
          key={entry.id}
          className="flex items-center gap-2 border-b border-white/5 py-1 text-sm leading-tight text-white"
        >
          <span className="w-5 text-right text-[10px] tabular-nums text-white/40">
            {entry.position}
          </span>
          <span className="font-medium">{entry.user_name}</span>
        </div>
      ))}
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

  // Empty = render nothing (fully transparent for OBS)
  if (isEmpty) return null

  const remaining = state!.total_active - state!.current_batch.length - state!.next_batch.length

  return (
    <div className="inline-block bg-transparent p-2 font-sans">
      <PlayerList entries={state!.current_batch} label="現在上場" />
      <PlayerList entries={state!.next_batch} label="下一批" />
      {remaining > 0 && <div className="text-[10px] text-white/30">+{remaining} 人排隊中</div>}
    </div>
  )
}
