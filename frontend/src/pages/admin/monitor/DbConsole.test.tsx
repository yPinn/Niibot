import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import { type DbQueryResult, type DbTable, getDbSchema, runDbQuery } from '@/api/admin'

import { DbConsole } from './DbConsole'

vi.mock('@/api/admin')

const mockSchema = getDbSchema as MockedFunction<typeof getDbSchema>
const mockRun = runDbQuery as MockedFunction<typeof runDbQuery>

const SCHEMA: DbTable[] = [
  {
    name: 'channels',
    kind: 'table',
    approx_rows: 12,
    has_hidden_columns: false,
    is_empty: false,
    columns: [
      { name: 'channel_id', type: 'text' },
      { name: 'enabled', type: 'boolean' },
    ],
  },
  {
    name: 'memberships',
    kind: 'table',
    approx_rows: 5,
    has_hidden_columns: false,
    is_empty: false,
    columns: [{ name: 'status', type: 'text' }],
  },
  {
    name: 'tokens',
    kind: 'table',
    approx_rows: 9,
    has_hidden_columns: true,
    is_empty: false,
    columns: [
      { name: 'user_id', type: 'text' },
      { name: 'scopes', type: 'text' },
    ],
  },
  {
    name: 'game_queue_entries',
    kind: 'table',
    approx_rows: null,
    has_hidden_columns: false,
    is_empty: true,
    columns: [{ name: 'id', type: 'text' }],
  },
]

const RESULT: DbQueryResult = {
  columns: ['channel_id', 'enabled'],
  rows: [['abc', true]],
  row_count: 1,
  duration_ms: 3.2,
  truncated: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  mockSchema.mockResolvedValue(SCHEMA)
  mockRun.mockResolvedValue(RESULT)
})

describe('DbConsole', () => {
  it('lists tables from the schema endpoint', async () => {
    render(<DbConsole />)
    expect(await screen.findByText('channels')).toBeInTheDocument()
    expect(screen.getByText('memberships')).toBeInTheDocument()
  })

  it('hides empty tables by default and reveals them via the toggle', async () => {
    render(<DbConsole />)
    await screen.findByText('channels')
    expect(screen.queryByText('game_queue_entries')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('顯示 1 張空資料表'))
    expect(screen.getByText('game_queue_entries')).toBeInTheDocument()
  })

  it('a search term still surfaces empty tables', async () => {
    render(<DbConsole />)
    await screen.findByText('channels')
    fireEvent.change(screen.getByPlaceholderText('搜尋資料表…'), {
      target: { value: 'game_queue' },
    })
    expect(screen.getByText('game_queue_entries')).toBeInTheDocument()
  })

  it('filters the table list by the search box', async () => {
    render(<DbConsole />)
    await screen.findByText('channels')
    fireEvent.change(screen.getByPlaceholderText('搜尋資料表…'), { target: { value: 'memb' } })
    expect(screen.queryByText('channels')).not.toBeInTheDocument()
    expect(screen.getByText('memberships')).toBeInTheDocument()
  })

  it('runs SELECT * for a table when its name is clicked', async () => {
    render(<DbConsole />)
    fireEvent.click(await screen.findByText('memberships'))
    await waitFor(() =>
      expect(mockRun).toHaveBeenCalledWith('SELECT *\nFROM memberships\nLIMIT 50;')
    )
  })

  it('runs an explicit column list for a table with hidden columns', async () => {
    render(<DbConsole />)
    fireEvent.click(await screen.findByText('tokens'))
    await waitFor(() =>
      expect(mockRun).toHaveBeenCalledWith('SELECT user_id, scopes\nFROM tokens\nLIMIT 50;')
    )
  })

  it('shows a query error in the results area, not just the status bar', async () => {
    mockRun.mockRejectedValue(new Error('這個資料表或欄位是受保護的內容，無法查詢'))
    render(<DbConsole />)
    fireEvent.click(await screen.findByText('channels'))
    // Rendered both in the results panel and the status bar.
    await waitFor(() =>
      expect(
        screen.getAllByText('這個資料表或欄位是受保護的內容，無法查詢').length
      ).toBeGreaterThanOrEqual(2)
    )
  })

  it('inserts a column name into the editor when clicked', async () => {
    render(<DbConsole />)
    await screen.findByText('channels')
    fireEvent.click(screen.getAllByLabelText('展開欄位')[0])
    fireEvent.click(await screen.findByText('channel_id'))
    const editor = screen.getByPlaceholderText('SELECT ...') as HTMLTextAreaElement
    await waitFor(() => expect(editor.value).toContain('channel_id'))
  })

  it('shows the truncation note when the result is capped', async () => {
    mockRun.mockResolvedValue({ ...RESULT, truncated: true, row_count: 500 })
    render(<DbConsole />)
    fireEvent.click(await screen.findByText('channels'))
    expect(await screen.findByText(/已截斷至 500 列/)).toBeInTheDocument()
  })

  it('surfaces a schema load error', async () => {
    mockSchema.mockRejectedValue(new Error('boom'))
    render(<DbConsole />)
    expect(await screen.findByText('boom')).toBeInTheDocument()
  })
})
