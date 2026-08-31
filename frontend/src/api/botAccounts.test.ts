import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import {
  createBotInvite,
  declineBotInvite,
  getBotInviteStatus,
  getPublicBotInvite,
  listBotAccounts,
} from './botAccounts'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('bot account APIs', () => {
  afterEach(() => vi.restoreAllMocks())

  it('keeps every private request explicitly tenant-scoped', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ accounts: [] }))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            invite_id: 'invite-1',
            public_url: 'https://niibot.test/bot-invite/opaque?nonce=nonce',
            expires_at: '2026-08-31T12:00:00Z',
          },
          201
        )
      )
      .mockResolvedValueOnce(
        jsonResponse({
          invite_id: 'invite-1',
          status: 'pending',
          expires_at: '2026-08-31T12:00:00Z',
          consumed_at: null,
          account: null,
        })
      )

    await listBotAccounts('channel-a')
    await createBotInvite('channel-a')
    await getBotInviteStatus('channel-a', 'invite-1')

    expect(fetchMock.mock.calls.map(call => requestUrl(call[0]).pathname)).toEqual([
      '/api/tenants/channel-a/bot-accounts',
      '/api/tenants/channel-a/bot-accounts/invites',
      '/api/tenants/channel-a/bot-accounts/invites/invite-1',
    ])
    expect(fetchMock.mock.calls[1][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'bot-account-management' },
    })
  })

  it('loads and declines a public invite using both one-time capabilities', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        jsonResponse({
          channel_name: 'alice',
          display_name: 'Alice',
          purpose: 'link_new',
          status: 'pending',
          expires_at: '2026-08-31T12:00:00Z',
          required_scopes: ['user:bot'],
          oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
        })
      )
      .mockResolvedValueOnce(jsonResponse({ status: 'declined' }))

    const invite = await getPublicBotInvite('opaque', 'state-nonce')
    await declineBotInvite('opaque', 'state-nonce')

    expect(invite.channel_name).toBe('alice')
    const urls = fetchMock.mock.calls.map(call => requestUrl(call[0]))
    expect(urls[0].pathname).toBe('/api/public/bot-invites/opaque')
    expect(urls[0].searchParams.get('nonce')).toBe('state-nonce')
    expect(urls[1].pathname).toBe('/api/public/bot-invites/opaque/decline')
    expect(fetchMock.mock.calls[1][1]).toEqual({ method: 'POST' })
  })
})
