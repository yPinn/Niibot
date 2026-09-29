import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import { exportCommandCsv, previewCommandCsv } from './commandImport'

describe('command CSV API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('previews a CSV as multipart without overriding the boundary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ items: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const upload = new File(['command,response\nhello,Hello'], 'commands.csv', {
      type: 'text/csv',
    })

    await previewCommandCsv(upload)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/commands/import/csv/preview')
    const options = fetchMock.mock.calls[0][1]
    expect(options.headers).toBeUndefined()
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('upload')).toBe(upload)
  })

  it('downloads the portable CSV filename and body', async () => {
    const response = new Response('command,response\nhello,Hello', {
      status: 200,
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename="niibot-commands.csv"',
      },
    })
    const fetchMock = vi.fn().mockResolvedValue(response)
    vi.stubGlobal('fetch', fetchMock)

    const download = await exportCommandCsv()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/commands/import/csv/export')
    expect(download.filename).toBe('niibot-commands.csv')
    expect(await download.blob.text()).toContain('hello,Hello')
  })
})
