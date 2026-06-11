import type { LogLine } from '@/api/admin'
import { sanitizeAnsiHtml } from '@/lib/sanitize'

import {
  ansiConverter,
  hasAnsi,
  lineColor,
  parseDockerTs,
  parsePgPrefix,
  parsePyBody,
  parsePyPrefix,
  pgContentColor,
  pgLevelColor,
  pyContentColor,
  pyLevelColor,
  stripAnsi,
  trimLeadingSpaces,
} from './logParsers'

export function LogLineRow({
  line,
  index,
  isPgMode,
}: {
  line: LogLine
  index: number
  isPgMode: boolean
}) {
  const { ts, msg } = parseDockerTs(line.text)
  const raw = msg || line.text
  const pg = parsePgPrefix(raw)
  const py = !pg ? parsePyPrefix(raw) : null
  const pyBody = py ? parsePyBody(py.body) : null
  const isOwn = pyBody?.isOwn ?? false
  // Continuation lines (no recognized prefix) carry Rich's column-alignment spaces — strip them.
  const content = pg ? pg.body : py ? (pyBody?.message ?? py.body) : trimLeadingSpaces(raw)

  const colored = hasAnsi(content) ? sanitizeAnsiHtml(ansiConverter.toHtml(content)) : null

  // When a structured level is known (py/pg), prefer level-based color over keyword scanning.
  // Use content color functions (not label colors) so body text has proper readable brightness.
  // In pg mode, unstructured lines (docker metadata/timestamps) are dimmed to distinguish from pg LOG.
  const fallbackColor = colored
    ? ''
    : py
      ? pyContentColor(py.level)
      : pg
        ? pgContentColor(pg.level)
        : isPgMode
          ? 'text-log-dim'
          : lineColor(stripAnsi(content))

  return (
    <div className="flex gap-2 min-w-0 hover:bg-white/5 px-3 py-px group">
      <span className="text-muted-foreground/50 shrink-0 select-none w-10 text-right tabular-nums group-hover:text-muted-foreground/70">
        {index + 1}
      </span>
      <span className="text-muted-foreground/70 shrink-0 tabular-nums w-36">{ts}</span>
      {pg && (
        <>
          <span className="text-muted-foreground/35 shrink-0 tabular-nums select-none w-10 text-right">
            [{pg.pid}]
          </span>
          <span className={`shrink-0 font-semibold select-none w-14 ${pgLevelColor(pg.level)}`}>
            {pg.level}
          </span>
        </>
      )}
      {py && (
        <>
          <span
            className={`shrink-0 font-semibold select-none w-16 ${
              isOwn || /^(ERROR|CRITICAL|FATAL|WARNING)$/.test(py.level)
                ? pyLevelColor(py.level)
                : 'text-muted-foreground/40'
            }`}
          >
            {py.level}
          </span>
          <span className="shrink-0 w-44 overflow-hidden select-none font-mono">
            {pyBody && (
              <span className={isOwn ? 'text-cyan-400/80' : 'text-muted-foreground/35'}>
                {pyBody.module}
              </span>
            )}
          </span>
        </>
      )}
      {!pg &&
        !py &&
        (isPgMode ? (
          <>
            <span className="w-10 shrink-0" />
            <span className="w-14 shrink-0" />
          </>
        ) : (
          <>
            <span className="w-16 shrink-0" />
            <span className="w-44 shrink-0" />
          </>
        ))}
      {colored ? (
        <span className="whitespace-pre min-w-0" dangerouslySetInnerHTML={{ __html: colored }} />
      ) : (
        <span className={`${fallbackColor} whitespace-pre min-w-0`}>{stripAnsi(content)}</span>
      )}
    </div>
  )
}
