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
  it('shows membership and monitoring status without opening details', () => {
    render(<ChannelCard ch={ACTIVE_CHANNEL} onSuspend={vi.fn()} />)

    expect(screen.getByText('使用中')).toBeInTheDocument()
    expect(screen.getByText('監控正常')).toBeInTheDocument()
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

  it('keeps a suspended identity readable and labels the stopped monitoring state', () => {
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

    expect(screen.getByText('已停權')).toBeInTheDocument()
    expect(screen.getByText('監控已停止')).toBeInTheDocument()
    expect(screen.getByText(/帳號安全風險/)).toBeInTheDocument()
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
