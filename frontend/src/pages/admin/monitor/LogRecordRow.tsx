import { useState } from 'react'

import type { LogRecord } from '@/api/admin'
import { copyToClipboard } from '@/lib/clipboard'
import { sanitizeAnsiHtml } from '@/lib/sanitize'

import {
  ansiConverter,
  type EventClass,
  eventClassLabel,
  eventClassPillClass,
  formatLogTime,
  hasAnsi,
  levelColor,
  levelMessageColor,
  levelRowClass,
  parseEventClass,
  stripAnsi,
  trimChannelPrefix,
} from './logParsers'

/** Split `extra` into `event_class` (own pill, see below), `key=value` chips
 *  (primitives), and the keys we can't chip (objects / arrays) so nothing is
 *  silently dropped. */
function partitionExtra(extra: Record<string, unknown>): {
  eventClass: EventClass | null
  chips: [string, string][]
  complex: string[]
} {
  const { event_class, ...rest } = extra
  const chips: [string, string][] = []
  const complex: string[] = []
  for (const [k, v] of Object.entries(rest)) {
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      chips.push([k, String(v)])
    } else {
      complex.push(k)
    }
  }
  return { eventClass: parseEventClass(event_class), chips, complex }
}

export function LogRecordRow({ record, index }: { record: LogRecord; index: number }) {
  const [open, setOpen] = useState(false)
  const [showExtra, setShowExtra] = useState(false)
  const isRaw = record.source === 'raw'
  const isPg = record.source === 'postgres'
  const { level } = record

  let message: string
  let colored: string | null = null
  if (isRaw) {
    message = stripAnsi(record.message)
    colored = hasAnsi(record.message)
      ? sanitizeAnsiHtml(ansiConverter.toHtml(record.message))
      : null
  } else {
    message = trimChannelPrefix(record.message, record.channel)
  }

  const { eventClass, chips, complex } = partitionExtra(record.extra)
  const time = formatLogTime(record.ts)
  const modTitle = [record.logger, record.service].filter(Boolean).join(' · ') || undefined
  const hasMeta = Boolean(
    record.channel ||
    record.request_id ||
    record.code ||
    eventClass ||
    record.exception ||
    chips.length ||
    complex.length
  )

  return (
    <div
      className={`group flex gap-2 px-3 py-px hover:bg-white/5 ${levelRowClass(level, record.stream, isPg)}`}
    >
      {/* Left gutter — click the line number to copy the raw line.
          Hidden below `sm:` — on a narrow phone this gutter (line number +
          time + level, ~250px) leaves almost nothing for the message
          column; the line number is the least essential of the three. */}
      <button
        type="button"
        onClick={() => copyToClipboard(record.raw, '已複製原始行')}
        title="複製原始行"
        className="hidden w-12 shrink-0 select-none text-right tabular-nums text-muted-foreground/50 group-hover:text-muted-foreground/70 hover:text-foreground sm:block"
      >
        {index + 1}
      </button>
      <span
        className="w-24 shrink-0 tabular-nums text-muted-foreground/70"
        title={time ? `${time.date} ${time.time}` : record.ts || undefined}
      >
        {time ? time.time : '--:--:--'}
      </span>

      {isPg ? (
        <span className="w-12 shrink-0 select-none text-right tabular-nums text-muted-foreground/35">
          [{record.pid}]
        </span>
      ) : (
        <span
          className={`w-20 shrink-0 select-none font-semibold ${
            level === 'UNKNOWN' ? 'text-muted-foreground/40' : levelColor(level)
          }`}
        >
          {level === 'UNKNOWN' ? '' : level}
        </span>
      )}

      {/* Message column — mod tag + message, meta chips and traceback here.
          `flex-1 min-w-0` + wrapping keeps every line inside the viewport. */}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {colored ? (
          <span
            className="wrap-break-word whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html: colored }}
          />
        ) : (
          <div className="wrap-break-word whitespace-pre-wrap">
            {record.mod && (
              <span
                className={record.own ? 'text-cyan-400/80' : 'text-muted-foreground/40'}
                title={modTitle}
              >
                {record.mod}{' '}
              </span>
            )}
            <span className={levelMessageColor(level)}>{message}</span>
          </div>
        )}

        {hasMeta && (
          <div className="flex flex-wrap items-center gap-1.5 text-label">
            {record.channel && (
              <span
                className="rounded bg-muted-foreground/10 px-1.5 font-mono text-muted-foreground/70"
                // When the login was resolved from a numeric id, keep the id
                // reachable on hover — it's what you'd paste into a query.
                title={record.channel_name ? record.channel : undefined}
              >
                #{record.channel_name ?? record.channel}
              </span>
            )}
            {record.code && (
              <span className="rounded bg-muted-foreground/15 px-1.5 text-muted-foreground">
                {record.code}
              </span>
            )}
            {eventClass && (
              <span className={`rounded px-1.5 ${eventClassPillClass(eventClass)}`}>
                {eventClassLabel(eventClass)}
              </span>
            )}
            {chips.map(([k, v]) => (
              <span
                key={k}
                className="rounded bg-muted-foreground/10 px-1.5 font-mono text-muted-foreground/70"
              >
                {k}={v}
              </span>
            ))}
            {complex.length > 0 && (
              <button
                onClick={() => setShowExtra(s => !s)}
                className="rounded bg-muted-foreground/10 px-1.5 font-mono text-muted-foreground/70 hover:text-muted-foreground"
              >
                {showExtra ? '隱藏' : `+${complex.length}`} {complex.join(' ')}
              </button>
            )}
            {record.request_id && (
              <button
                onClick={() => copyToClipboard(record.request_id!, '已複製 request id')}
                className="rounded bg-muted-foreground/10 px-1.5 font-mono text-muted-foreground/70 hover:text-muted-foreground"
              >
                {record.request_id.slice(0, 8)} ⧉
              </button>
            )}
            {record.exception && (
              <button
                onClick={() => setOpen(o => !o)}
                className="rounded bg-status-offline/15 px-1.5 text-status-offline"
              >
                {open ? '隱藏 traceback' : '展開 traceback'}
              </button>
            )}
          </div>
        )}

        {showExtra && complex.length > 0 && (
          <pre className="overflow-x-auto rounded bg-black/30 p-2 text-sub text-muted-foreground/80">
            {JSON.stringify(Object.fromEntries(complex.map(k => [k, record.extra[k]])), null, 2)}
          </pre>
        )}

        {open && record.exception && (
          <pre className="overflow-x-auto rounded bg-black/30 p-2 text-sub text-status-offline/90">
            {record.exception}
          </pre>
        )}
      </div>
    </div>
  )
}
