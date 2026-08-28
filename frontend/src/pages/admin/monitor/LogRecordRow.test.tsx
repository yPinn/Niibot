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
})
