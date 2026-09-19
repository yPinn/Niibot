import { useCallback, useEffect, useState } from 'react'

import { type EmoteItem, getChannelEmotes, type OtherChannelEmotes } from '@/api/emotes'

export interface UseChannelEmotesResult {
  emotes: EmoteItem[]
  otherChannels: OtherChannelEmotes[]
  botUserId: string
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Fetches the current channel's bot-account emote availability, backed by
 * `apiCache` so opening multiple template editors (commands/events/AI) on the
 * same page load only issues one request.
 *
 * `enabled` gates the fetch — pass whether the consuming sheet/section is
 * actually open, so listing pages don't pay for emotes nobody is picking yet.
 */
export function useChannelEmotes(enabled = true): UseChannelEmotesResult {
  const [emotes, setEmotes] = useState<EmoteItem[]>([])
  const [otherChannels, setOtherChannels] = useState<OtherChannelEmotes[]>([])
  const [botUserId, setBotUserId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const res = await getChannelEmotes({ forceRefresh: version > 0 })
        if (cancelled) return
        setEmotes(res.emotes)
        setOtherChannels(res.other_channels)
        setBotUserId(res.bot_user_id)
      } catch {
        if (!cancelled) setError('載入表情符號失敗')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [enabled, version])

  const reload = useCallback(() => setVersion(v => v + 1), [])

  return { emotes, otherChannels, botUserId, loading, error, reload }
}
