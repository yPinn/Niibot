import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import {
  type ClientErrorEvent,
  type ClientErrorGroup,
  getClientErrorEvents,
  getClientErrorGroups,
} from '@/api/admin'

import { ClientErrorsPanel } from './ClientErrorsPanel'

vi.mock('@/api/admin')

const mockGroups = getClientErrorGroups as MockedFunction<typeof getClientErrorGroups>
const mockEvents = getClientErrorEvents as MockedFunction<typeof getClientErrorEvents>

const GROUP: ClientErrorGroup = {
  fingerprint: 'fp1',
  count: 4,
  first_seen: new Date(Date.now() - 3_600_000).toISOString(),
  last_seen: new Date(Date.now() - 120_000).toISOString(),
  kind: 'react',
  message: 'Cannot read properties of undefined',
  route: '/dashboard',
  error_code: null,
  http_status: null,
  app_version: '1.2.3',
  request_id: 'req-abc',
}

const EVENT: ClientErrorEvent = {
  occurred_at: new Date().toISOString(),
  kind: 'react',
  message: 'Cannot read properties of undefined',
  stack: 'at Foo (bundle.js:1:2)',
  component_stack: 'in Foo',
  url: 'https://niibot.tv/dashboard',
  route: '/dashboard',
  request_id: 'req-abc',
  error_code: null,
  http_status: null,
  user_id: null,
  user_agent: 'UA',
  app_version: '1.2.3',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGroups.mockResolvedValue([GROUP])
  mockEvents.mockResolvedValue([EVENT])
})

describe('ClientErrorsPanel', () => {
  it('lists grouped errors with count and message', async () => {
    render(<ClientErrorsPanel onTraceRequestId={vi.fn()} />)
    expect(await screen.findByText('Cannot read properties of undefined')).toBeInTheDocument()
    expect(screen.getByText('×4')).toBeInTheDocument()
  })

  it('shows an empty state when there are no errors', async () => {
    mockGroups.mockResolvedValue([])
    render(<ClientErrorsPanel onTraceRequestId={vi.fn()} />)
    expect(await screen.findByText('這段期間沒有前端錯誤')).toBeInTheDocument()
  })

  it('fetches and shows event detail (stack) on expand', async () => {
    render(<ClientErrorsPanel onTraceRequestId={vi.fn()} />)
    fireEvent.click(await screen.findByText('Cannot read properties of undefined'))
    expect(await screen.findByText('at Foo (bundle.js:1:2)')).toBeInTheDocument()
    expect(mockEvents).toHaveBeenCalledWith('fp1')
  })

  it('calls onTraceRequestId with the full request id from an event', async () => {
    const onTrace = vi.fn()
    render(<ClientErrorsPanel onTraceRequestId={onTrace} />)
    fireEvent.click(await screen.findByText('Cannot read properties of undefined'))
    fireEvent.click(await screen.findByTitle('在 API log 中追蹤此請求'))
    expect(onTrace).toHaveBeenCalledWith('req-abc')
  })

  it('refetches with the kind filter applied', async () => {
    render(<ClientErrorsPanel onTraceRequestId={vi.fn()} />)
    await screen.findByText('Cannot read properties of undefined')
    fireEvent.click(screen.getByRole('button', { name: 'API' }))
    await waitFor(() =>
      expect(mockGroups).toHaveBeenLastCalledWith({ sinceHours: 168, kind: 'api' })
    )
  })
})
