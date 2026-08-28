import { useState } from 'react'

import type { LogRecord } from '@/api/admin'
import { copyToClipboard } from '@/lib/clipboard'
import { sanitizeAnsiHtml } from '@/lib/sanitize'

import { ansiConverter, hasAnsi, levelColor, stripAnsi, trimChannelPrefix } from './logParsers'

export function LogRecordRow({ record, index }: { record: LogRecord; index: number }) {
  const [open, setOpen] = useState(false)
  const isRaw = record.source === 'raw'
  const message = isRaw ? record.message : trimChannelPrefix(record.message, record.channel)

  const colored = isRaw && hasAnsi(message) ? sanitizeAnsiHtml(ansiConverter.toHtml(message)) : null

  return (
    <div className="group flex flex-col gap-0.5 px-3 py-px hover:bg-white/5">
      <div className="flex min-w-0 gap-2">
        <span className="w-10 shrink-0 select-none text-right tabular-nums text-muted-foreground/50 group-hover:text-muted-foreground/70">
          {index + 1}
        </span>
        <span className="w-36 shrink-0 tabular-nums text-muted-foreground/70">{record.ts}</span>

        {record.source === 'postgres' ? (
          <span className="w-10 shrink-0 select-none text-right tabular-nums text-muted-foreground/35">
            [{record.pid}]
          </span>
        ) : (
          <span
            className={`w-16 shrink-0 select-none font-semibold ${
              record.level === 'UNKNOWN' ? 'text-muted-foreground/40' : levelColor(record.level)
            }`}
          >
            {record.level === 'UNKNOWN' ? '' : record.level}
          </span>
        )}

        <span
          className={`w-40 shrink-0 overflow-hidden font-mono ${
            record.own ? 'text-cyan-400/80' : 'text-muted-foreground/35'
          }`}
        >
          {record.mod}
        </span>

        {colored ? (
          <span className="min-w-0 whitespace-pre" dangerouslySetInnerHTML={{ __html: colored }} />
        ) : (
          <span className={`min-w-0 whitespace-pre ${levelColor(record.level)}`}>
            {isRaw ? stripAnsi(message) : message}
          </span>
        )}
      </div>

      {(record.request_id || record.code || record.exception) && (
        <div className="flex flex-wrap items-center gap-1.5 pl-[12.5rem] text-label">
          {record.code && (
            <span className="rounded bg-muted-foreground/15 px-1.5 text-muted-foreground">
              {record.code}
            </span>
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

      {open && record.exception && (
        <pre className="ml-[12.5rem] overflow-x-auto rounded bg-black/30 p-2 text-label text-status-offline/90">
          {record.exception}
        </pre>
      )}
    </div>
  )
}
