import { useState } from 'react'

import type { EmoteItem, OtherChannelEmotes } from '@/api/emotes'

export interface EmoteInserterProps {
  emotes: EmoteItem[]
  /** Emotes the bot account has unlocked on OTHER channels (subscription
   * emotes are usable anywhere once unlocked), grouped by source channel. */
  otherChannels?: OtherChannelEmotes[]
  /** Same shape as `useInputInsert`'s `insertText` — drop-in compatible. */
  onInsert: (text: string) => void
  /** Section label — defaults to "可用表情（點擊插入）". */
  label?: string
  loading?: boolean
  error?: string | null
}

const COLLAPSED_COUNT = 16

function EmoteChipRow({
  emotes,
  onInsert,
}: {
  emotes: EmoteItem[]
  onInsert: (text: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? emotes : emotes.slice(0, COLLAPSED_COUNT)
  const remaining = emotes.length - visible.length

  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map(emote => (
        <button
          key={emote.id}
          type="button"
          title={emote.name}
          onClick={() => onInsert(`${emote.name} `)}
          className="cursor-pointer rounded-md border p-0.5 transition-colors hover:bg-accent"
        >
          <img src={emote.url} alt={emote.name} className="h-6 w-6 object-contain" loading="lazy" />
        </button>
      ))}
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="cursor-pointer rounded-md border px-2 py-0.5 text-label text-muted-foreground transition-colors hover:bg-accent"
        >
          +{remaining}
        </button>
      )}
    </div>
  )
}

function OtherChannelGroup({
  group,
  onInsert,
}: {
  group: OtherChannelEmotes
  onInsert: (text: string) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex cursor-pointer items-center gap-1.5 text-label text-muted-foreground select-none"
      >
        <img src={group.avatar} alt="" className="h-4 w-4 rounded-full" loading="lazy" />
        <span>{group.display_name || group.channel_name}</span>
        <span>({group.emotes.length})</span>
      </button>
      {open && <EmoteChipRow emotes={group.emotes} onInsert={onInsert} />}
    </div>
  )
}

/**
 * A row of clickable emote chips that insert an emote's name into a text
 * field, sized and styled to sit alongside `VariableInserter`.
 *
 * Unlike `EmoteChip` (a display/toggle component in the AI settings page),
 * unavailable emotes are hidden rather than dimmed — inserting an emote name
 * the bot's current account can't actually send would just produce a broken
 * word in chat, so offering it here is a trap, not a diagnostic.
 *
 * `otherChannels` covers emotes the bot unlocked elsewhere on Twitch (mainly
 * subscription emotes, which work in any chat once unlocked) — each source
 * channel collapses behind its own header so subscribing to many channels
 * doesn't dump a wall of icons into the editor by default.
 */
export function EmoteInserter({
  emotes,
  otherChannels = [],
  onInsert,
  label = '可用表情（點擊插入）',
  loading = false,
  error = null,
}: EmoteInserterProps) {
  // Unavailable emotes (e.g. a subscription tier the bot isn't subscribed to)
  // are silently dropped, not called out — "not subscribed" already explains
  // itself; a count of what's missing isn't actionable here.
  const available = emotes.filter(e => e.available)
  // emote_type is 'globals' for Twitch's global set; everything else
  // (follower/subscriptions/bitstier) belongs to this channel specifically —
  // keep them visually separate so a channel emote and a global emote aren't
  // mistaken for one flat pool.
  const channelEmotes = available.filter(e => e.emote_type !== 'globals')
  const globalEmotes = available.filter(e => e.emote_type === 'globals')

  if (loading) {
    return <span className="text-label text-muted-foreground select-none">{label}載入中...</span>
  }
  if (error) {
    return <span className="text-label text-destructive select-none">{error}</span>
  }
  if (available.length === 0 && otherChannels.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label text-muted-foreground select-none">{label}</span>
      {channelEmotes.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-label text-muted-foreground select-none">本頻道貼圖</span>
          <EmoteChipRow emotes={channelEmotes} onInsert={onInsert} />
        </div>
      )}
      {globalEmotes.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-label text-muted-foreground select-none">全球貼圖</span>
          <EmoteChipRow emotes={globalEmotes} onInsert={onInsert} />
        </div>
      )}
      {otherChannels.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t pt-1.5">
          {otherChannels.map(group => (
            <OtherChannelGroup key={group.channel_id} group={group} onInsert={onInsert} />
          ))}
        </div>
      )}
    </div>
  )
}
