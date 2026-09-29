import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { TwitchCapabilitySnapshot } from '@/api/botAccounts'
import type { CommandConfig } from '@/api/commands'

import { CommandSetupNotice } from './CommandSetupNotice'

function command(enabled: boolean): CommandConfig {
  return {
    id: null,
    channel_id: 'channel-1',
    command_name: 'subage',
    command_type: 'builtin',
    enabled,
    custom_response: null,
    cooldown: 15,
    min_role: 'everyone',
    aliases: '訂閱資訊',
    usage_count: 0,
    description: '查看累積訂閱月數與目前方案',
    detail: '回覆累積訂閱月數、方案與禮物訂閱狀態。',
    usage: '!subage',
    preview_input: '!subage',
    preview_output: '@小霓 累積訂閱 14 個月，目前是 T2 訂閱者',
    audience: 'viewer',
    public_visible: true,
    display_order: 0,
    category_label: '觀眾查詢',
    integration_kind: 'twitch_capability',
    integration_label: 'Twitch 訂閱資料',
    capability_requirements: [
      { capability_key: 'subscriptions', mode: 'all', requires_bot_moderator: false },
    ],
    external_conditions: [],
  }
}

const snapshot: TwitchCapabilitySnapshot = {
  broadcaster_status: 'valid',
  bot_status: 'valid',
  bot_user_id: 'bot-1',
  capabilities: [
    {
      key: 'subscriptions',
      label: '訂閱資料',
      credential: 'broadcaster',
      available: false,
      missing_scopes: ['channel:read:subscriptions'],
      core: false,
    },
  ],
}

describe('CommandSetupNotice', () => {
  it('stays hidden when only disabled commands need setup', () => {
    render(
      <MemoryRouter>
        <CommandSetupNotice commands={[command(false)]} snapshot={snapshot} botModerator={false} />
      </MemoryRouter>
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows one actionable message without capability internals', () => {
    render(
      <MemoryRouter>
        <CommandSetupNotice commands={[command(true)]} snapshot={snapshot} botModerator={null} />
      </MemoryRouter>
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('部分指令功能尚未就緒')
    expect(alert).toHaveTextContent('完成設定後即可使用完整功能')
    expect(screen.getByRole('link', { name: '檢查設定' })).toHaveAttribute('href', '/settings')
    expect(alert).not.toHaveTextContent('Twitch 訂閱資料')
    expect(alert).not.toHaveTextContent('channel:read:subscriptions')
    expect(alert).not.toHaveTextContent('credential')
  })

  it('shows the same generic message when an enabled command needs bot moderator', () => {
    const moderatorCommand = command(true)
    moderatorCommand.capability_requirements = [
      { capability_key: 'subscriptions', mode: 'all', requires_bot_moderator: true },
    ]
    const readySnapshot = {
      ...snapshot,
      capabilities: snapshot.capabilities.map(capability => ({
        ...capability,
        available: true,
        missing_scopes: [],
      })),
    }

    render(
      <MemoryRouter>
        <CommandSetupNotice
          commands={[moderatorCommand]}
          snapshot={readySnapshot}
          botModerator={false}
        />
      </MemoryRouter>
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('部分指令功能尚未就緒')
    expect(alert).not.toHaveTextContent('Mod')
    expect(alert).not.toHaveTextContent('subscriptions')
  })

  it('shows the same generic message when a core capability is unavailable', () => {
    const coreSnapshot = {
      ...snapshot,
      capabilities: [
        {
          ...snapshot.capabilities[0],
          key: 'chat',
          label: '聊天室連線',
          core: true,
        },
      ],
    }

    render(
      <MemoryRouter>
        <CommandSetupNotice
          commands={[command(true)]}
          snapshot={coreSnapshot}
          botModerator={true}
        />
      </MemoryRouter>
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('部分指令功能尚未就緒')
    expect(alert).not.toHaveTextContent('聊天室連線')
    expect(alert).not.toHaveTextContent('chat')
  })
})
