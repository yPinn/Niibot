import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { LogRecord } from '@/api/admin'

import { LogRecordRow } from './LogRecordRow'

const base: LogRecord = {
  stream: 'stdout',
  ts: '2026-08-28 08:05:19',
  level: 'INFO',
  source: 'json',
  message: 'hello',
  logger: 'routers.x',
  mod: 'x',
  own: true,
  service: 'api',
  request_id: null,
  channel: null,
  code: null,
  pid: null,
  exception: null,
  extra: {},
  raw: '{}',
}

describe('LogRecordRow', () => {
  it('renders ts / level / mod / message for a json record', () => {
    render(<LogRecordRow record={base} index={0} />)
    expect(screen.getByText('INFO')).toBeInTheDocument()
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.getByText('x')).toBeInTheDocument()
  })

  it('strips a redundant [channel] prefix', () => {
    render(
      <LogRecordRow record={{ ...base, channel: 'foo', message: '[foo] timer fired' }} index={0} />
    )
    expect(screen.getByText('timer fired')).toBeInTheDocument()
  })

  it('shows a code badge and a collapsed traceback', () => {
    render(
      <LogRecordRow
        record={{
          ...base,
          level: 'ERROR',
          code: 'TIMER.NOT_FOUND',
          exception: 'Traceback...\nValueError: nope',
        }}
        index={0}
      />
    )
    expect(screen.getByText('TIMER.NOT_FOUND')).toBeInTheDocument()
    expect(screen.getByText('展開 traceback')).toBeInTheDocument()
    expect(screen.queryByText(/ValueError: nope/)).not.toBeInTheDocument()
  })

  it('renders a postgres record with its pid', () => {
    render(
      <LogRecordRow
        record={{ ...base, source: 'postgres', pid: '28', level: 'ERROR', message: 'deadlock' }}
        index={2}
      />
    )
    expect(screen.getByText('[28]')).toBeInTheDocument()
    expect(screen.getByText('deadlock')).toBeInTheDocument()
  })

  it('renders primitive extra fields as key=value chips', () => {
    render(
      <LogRecordRow
        record={{
          ...base,
          extra: { http_method: 'POST', http_path: '/api/timers', retries: 2, payload: { a: 1 } },
        }}
        index={0}
      />
    )
    expect(screen.getByText('http_method=POST')).toBeInTheDocument()
    expect(screen.getByText('http_path=/api/timers')).toBeInTheDocument()
    expect(screen.getByText('retries=2')).toBeInTheDocument()
    // non-primitive values are not chipped as key=value…
    expect(screen.queryByText(/payload=/)).not.toBeInTheDocument()
    // …but are surfaced behind a toggle so nothing is silently dropped
    expect(screen.getByRole('button', { name: /payload/ })).toBeInTheDocument()
  })

  it('tints an ERROR row and keeps the message body neutral', () => {
    const { container } = render(
      <LogRecordRow record={{ ...base, level: 'ERROR', message: 'boom' }} index={0} />
    )
    expect(container.firstChild).toHaveClass('bg-status-offline/8')
    expect(container.firstChild).toHaveClass('border-status-offline/60')
    expect(screen.getByText('boom')).toHaveClass('text-log-base')
  })

  it('gives a non-error stderr row a neutral rule, not a red one', () => {
    const { container } = render(<LogRecordRow record={{ ...base, stream: 'stderr' }} index={0} />)
    expect(container.firstChild).toHaveClass('border-muted-foreground/30')
    expect(container.firstChild).not.toHaveClass('border-status-offline/60')
  })

  it('shows a #channel chip when the record carries a channel', () => {
    render(
      <LogRecordRow record={{ ...base, channel: 'foo', message: 'plain message' }} index={0} />
    )
    expect(screen.getByText('#foo')).toBeInTheDocument()
  })

  it('renders a console-source record as structured (no ANSI decode)', () => {
    render(
      <LogRecordRow
        record={{
          ...base,
          source: 'console',
          level: 'INFO',
          mod: 'timers_router',
          own: true,
          message: 'Will watch for changes',
        }}
        index={0}
      />
    )
    expect(screen.getByText('INFO')).toBeInTheDocument()
    expect(screen.getByText('Will watch for changes')).toBeInTheDocument()
    expect(screen.getByText('timers_router')).toBeInTheDocument()
  })

  it('exposes the raw line via the line-number button', () => {
    render(<LogRecordRow record={base} index={0} />)
    expect(screen.getByTitle('複製原始行')).toBeInTheDocument()
  })
})
