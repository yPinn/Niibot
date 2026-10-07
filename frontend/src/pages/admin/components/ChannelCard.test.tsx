import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import type { AdminChannel } from '@/api/admin'

import { ChannelCard } from './ChannelCard'

const ACTIVE_CHANNEL: AdminChannel = {
  id: 'channel-1',
  name: 'streamer',
  display_name: 'Streamer',
  avatar: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',
  offline_image_url: '',
  is_live: false,
  is_enabled: true,
  mod_status: 'mod',
  is_bot: false,
  granted_scopes: [],
  missing_scopes: [],
  membership_status: 'active',
  membership_reason: null,
  owner_user_id: 'user-1',
}

beforeAll(() => {
  Element.prototype.hasPointerCapture = vi.fn().mockReturnValue(false)
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

async function openDetails(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /Streamer/ }))
}

describe('ChannelCard membership actions', () => {
  it('keeps a healthy card badge-free but announces its status', () => {
    render(<ChannelCard ch={{ ...ACTIVE_CHANNEL, is_live: true }} onSuspend={vi.fn()} />)

    expect(screen.queryByText('使用中')).not.toBeInTheDocument()
    expect(screen.queryByText('監控正常')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Streamer，直播中，監控正常' })).toBeInTheDocument()
  })

  it('flags an unreachable Twitch status as an issue rather than healthy', () => {
    render(<ChannelCard ch={{ ...ACTIVE_CHANNEL, mod_status: 'provider_unavailable' }} />)

    expect(screen.getByText('無法確認狀態')).toBeInTheDocument()
  })

  it('preserves the 16:9 media card and full-bleed offline background', () => {
    const { container } = render(
      <ChannelCard
        ch={{ ...ACTIVE_CHANNEL, offline_image_url: 'https://example.com/offline.jpg' }}
        onSuspend={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /Streamer/ })).toHaveClass('aspect-video')
    expect(container.querySelector('img[alt=""]')).toHaveClass(
      'absolute',
      'inset-0',
      'size-full',
      'object-cover'
    )
  })

  it('announces a suspended card and keeps the reason for the details view', () => {
    render(
      <ChannelCard
        ch={{
          ...ACTIVE_CHANNEL,
          is_enabled: false,
          membership_status: 'suspended',
          membership_reason: '帳號安全風險',
        }}
        onReinstate={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Streamer，已停權' })).toBeInTheDocument()
    expect(screen.queryByText(/帳號安全風險/)).not.toBeInTheDocument()
  })

  it('lists only the missing scopes in the details view', async () => {
    const user = userEvent.setup()
    render(
      <ChannelCard
        ch={{
          ...ACTIVE_CHANNEL,
          granted_scopes: ['user:read:chat'],
          missing_scopes: ['bits:read'],
        }}
      />
    )

    await openDetails(user)

    expect(screen.getByText('bits:read')).toBeInTheDocument()
    expect(screen.queryByText('user:read:chat')).not.toBeInTheDocument()
  })

  it('shows missing permission count as an actionable status', () => {
    render(
      <ChannelCard
        ch={{
          ...ACTIVE_CHANNEL,
          mod_status: 'scope_error',
          missing_scopes: ['scope:a', 'scope:b'],
        }}
        onSuspend={vi.fn()}
      />
    )

    expect(screen.getByText('缺少 2 項權限')).toBeInTheDocument()
  })

  it('uses a common reason preset and lets the admin edit it before suspending', async () => {
    const user = userEvent.setup()
    const onSuspend = vi.fn().mockResolvedValue(true)
    render(<ChannelCard ch={ACTIVE_CHANNEL} onSuspend={onSuspend} />)

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '停權使用者' }))

    const confirm = screen.getByRole('button', { name: '確認停權' })
    expect(confirm).toBeDisabled()

    await user.click(screen.getByRole('combobox', { name: '常見原因' }))
    await user.click(screen.getByRole('option', { name: '違反使用規範' }))

    const reason = screen.getByRole('textbox', { name: '停權原因' })
    expect(reason).toHaveValue('違反使用規範')
    await user.type(reason, '：多次警告未改善')
    await user.click(confirm)

    expect(onSuspend).toHaveBeenCalledWith(ACTIVE_CHANNEL, '違反使用規範：多次警告未改善')
    expect(screen.queryByRole('dialog', { name: /停權 Streamer/ })).not.toBeInTheDocument()
  })

  it('keeps the dialog and entered reason when suspension fails', async () => {
    const user = userEvent.setup()
    const onSuspend = vi.fn().mockResolvedValue(false)
    render(<ChannelCard ch={ACTIVE_CHANNEL} onSuspend={onSuspend} />)

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '停權使用者' }))
    const reason = screen.getByRole('textbox', { name: '停權原因' })
    await user.type(reason, '人工複查')
    await user.click(screen.getByRole('button', { name: '確認停權' }))

    expect(screen.getByRole('dialog', { name: /停權 Streamer/ })).toBeInTheDocument()
    expect(reason).toHaveValue('人工複查')
  })

  it('shows the recorded reason and only the reinstate action for a suspended user', async () => {
    const user = userEvent.setup()
    render(
      <ChannelCard
        ch={{
          ...ACTIVE_CHANNEL,
          is_enabled: false,
          membership_status: 'suspended',
          membership_reason: '帳號安全風險',
        }}
        onSuspend={vi.fn()}
        onReinstate={vi.fn()}
      />
    )

    await openDetails(user)

    expect(screen.getByText('帳號安全風險')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '恢復授權' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停權使用者' })).not.toBeInTheDocument()
  })
})

describe('ChannelCard fix actions', () => {
  it("links the user's name to their Twitch channel", async () => {
    const user = userEvent.setup()
    render(<ChannelCard ch={{ ...ACTIVE_CHANNEL, mod_status: 'token_error' }} />)

    await openDetails(user)

    const link = screen.getByRole('link', { name: 'Streamer' })
    expect(link).toHaveAttribute('href', 'https://www.twitch.tv/streamer')
    expect(link).toHaveAttribute('target', '_blank')
    // The broadcaster is already prompted in-app; no copy-to-send step here.
    expect(screen.queryByRole('button', { name: /複製/ })).not.toBeInTheDocument()
  })

  it('rechecks a channel whose Twitch status could not be confirmed', async () => {
    const user = userEvent.setup()
    const onRecheck = vi.fn().mockResolvedValue(undefined)
    render(
      <ChannelCard
        ch={{ ...ACTIVE_CHANNEL, mod_status: 'provider_unavailable' }}
        onRecheck={onRecheck}
      />
    )

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '重新檢查' }))

    expect(onRecheck).toHaveBeenCalled()
  })

  it('approves a pending user from the card and closes the dialog', async () => {
    const user = userEvent.setup()
    const pending: AdminChannel = {
      ...ACTIVE_CHANNEL,
      is_enabled: false,
      membership_status: 'pending',
    }
    const onApprove = vi.fn().mockResolvedValue(true)
    render(<ChannelCard ch={pending} onApprove={onApprove} onReject={vi.fn()} />)

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '核准' }))

    expect(onApprove).toHaveBeenCalledWith(pending)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('requires a second click to reject a pending user', async () => {
    const user = userEvent.setup()
    const pending: AdminChannel = {
      ...ACTIVE_CHANNEL,
      is_enabled: false,
      membership_status: 'pending',
    }
    const onReject = vi.fn().mockResolvedValue(true)
    render(<ChannelCard ch={pending} onApprove={vi.fn()} onReject={onReject} />)

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '拒絕' }))
    expect(onReject).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '確認拒絕' }))
    expect(onReject).toHaveBeenCalledWith(pending)
  })

  it('keeps the dialog open when a membership action fails', async () => {
    const user = userEvent.setup()
    render(
      <ChannelCard
        ch={{ ...ACTIVE_CHANNEL, is_enabled: false, membership_status: 'suspended' }}
        onReinstate={vi.fn().mockResolvedValue(false)}
      />
    )

    await openDetails(user)
    await user.click(screen.getByRole('button', { name: '恢復授權' }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
