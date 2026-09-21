import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import {
  applyCheckinImport,
  clearCheckinData,
  exportCheckinData,
  getCheckinDataSummary,
  getCheckinLeaderboard,
  getCheckinSettings,
  inspectCheckinImportColumns,
  previewCheckinImport,
  updateCheckinSettings,
} from './checkin'

describe('check-in settings API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads settings for the authenticated tenant', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ timezone: 'Asia/Taipei' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCheckinSettings()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/settings')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('loads the authenticated tenant leaderboard', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue([]),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCheckinLeaderboard()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/leaderboard')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('updates shared templates with an explicit mutation header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ timezone: 'Asia/Tokyo' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const update = {
      timezone: 'Asia/Tokyo',
      success_template: '$(@user) 第 $(count) 天',
      duplicate_template: '$(@user) 今天已簽到',
      reply_delay_seconds: 5,
    }

    await updateCheckinSettings(update)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/settings')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-settings',
      },
      body: JSON.stringify(update),
    })
  })

  it('previews an XLSX upload as multipart without setting a content type boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ rows: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const upload = new File(['workbook'], 'checkins.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    await previewCheckinImport({
      source: 'chiwabots',
      sourceTimezone: 'Asia/Taipei',
      throughDate: '2026-09-10',
      upload,
      columnMapping: { username: 0, total_days: 1, last_checkin_date: 2 },
    })

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(
      '/api/checkin/import/summary/preview'
    )
    const options = fetchMock.mock.calls[0][1]
    expect(options.headers).toEqual({ 'X-Niibot-Action': 'checkin-import' })
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('upload')).toBe(upload)
    expect(options.body.get('source_timezone')).toBe('Asia/Taipei')
    expect(options.body.get('column_mapping')).toBe(
      '{"username":0,"total_days":1,"last_checkin_date":2}'
    )
  })

  it('inspects source headers before validating rows', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ headers: ['viewer', 'total', 'date'] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await inspectCheckinImportColumns({
      sheetUrl: 'https://docs.google.com/spreadsheets/d/abc123/edit?gid=0#gid=0',
    })

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(
      '/api/checkin/import/summary/columns'
    )
    const options = fetchMock.mock.calls[0][1]
    expect(options.headers).toEqual({ 'X-Niibot-Action': 'checkin-import' })
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('sheet_url')).toBe(
      'https://docs.google.com/spreadsheets/d/abc123/edit?gid=0#gid=0'
    )
  })

  it('applies only selected preview rows with the cutover confirmation', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ batch_id: 'batch-1', imported_rows: 1 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await applyCheckinImport('preview-1', ['row-1'], true)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/import/apply')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-import',
      },
      body: JSON.stringify({
        import_id: 'preview-1',
        selected_keys: ['row-1'],
        old_source_disabled: true,
      }),
    })
  })

  it('loads the owner-only data-management impact summary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ participant_count: 2 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCheckinDataSummary()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/data/summary')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('downloads the portable CSV filename from the response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('Username\r\nalice\r\n', {
        status: 200,
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition':
            'attachment; filename="niibot-checkins.csv"; filename*=UTF-8\'\'owner-checkins.csv',
        },
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const download = await exportCheckinData()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/data/export')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
    expect(download.filename).toBe('owner-checkins.csv')
    expect(await download.blob.text()).toContain('alice')
  })

  it('clears only the selected data scope with an explicit action header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ scope: 'imported' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await clearCheckinData('imported', 'owner_login')

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/data/clear')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-data',
      },
      body: JSON.stringify({ scope: 'imported', confirmation: 'owner_login' }),
    })
  })
})
