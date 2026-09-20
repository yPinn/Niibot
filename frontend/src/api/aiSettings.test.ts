import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import {
  AI_SETTINGS_DEFAULT,
  getTenantAISettings,
  patchTenantAISettings,
  resetTenantAISettings,
} from './aiSettings'
import { getTenantChannelEmotes } from './emotes'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('tenant AI settings APIs', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads AI settings and emotes from the selected workspace', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(AI_SETTINGS_DEFAULT))
      .mockResolvedValueOnce(
        jsonResponse({
          bot_user_id: 'bot-1',
          bot_token_available: true,
          emotes: [],
          other_channels: [],
        })
      )

    await getTenantAISettings('channel/a')
    await getTenantChannelEmotes('channel/a', { forceRefresh: true })

    expect(fetchMock.mock.calls.map(call => requestUrl(call[0]).pathname)).toEqual([
      '/api/tenants/channel%2Fa/ai/settings',
      '/api/tenants/channel%2Fa/emotes',
    ])
  })

  it('uses explicit action headers for tenant mutations', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(AI_SETTINGS_DEFAULT))
      .mockResolvedValueOnce(jsonResponse(AI_SETTINGS_DEFAULT))

    await patchTenantAISettings('channel-a', { bot_name: 'WorkspaceBot' })
    await resetTenantAISettings('channel-a')

    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'ai-settings',
      },
      body: JSON.stringify({ bot_name: 'WorkspaceBot' }),
    })
    expect(fetchMock.mock.calls[1][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'ai-settings' },
    })
  })
})
