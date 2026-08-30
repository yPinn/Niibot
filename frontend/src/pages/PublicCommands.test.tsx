import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/commands', () => ({ getPublicCommands: vi.fn() }))
vi.mock('@/components/layout/theme-provider', () => ({
  useTheme: () => ({ resolvedTheme: 'dark', setTheme: vi.fn() }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
import { getPublicCommands } from '@/api/commands'

import PublicCommands from './PublicCommands'

describe('PublicCommands', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getPublicCommands).mockResolvedValue({
      channel: { display_name: 'Streamer', profile_image_url: null },
      commands: [
        {
          name: '!help',
          description: '顯示可用指令',
          min_role: 'everyone',
          command_type: 'builtin',
          category_label: '常用互動',
        },
        {
          name: '!sub-only',
          description: '訂閱者指令',
          min_role: 'subscriber',
          command_type: 'custom',
          category_label: null,
        },
        {
          name: '!vip-only',
          description: 'VIP 指令',
          min_role: 'vip',
          command_type: 'custom',
          category_label: null,
        },
      ],
    })
  })

  it('groups viewer-facing commands by Twitch access role', async () => {
    render(
      <MemoryRouter initialEntries={['/streamer/commands']}>
        <Routes>
          <Route path="/:username/commands" element={<PublicCommands />} />
        </Routes>
      </MemoryRouter>
    )

    const everyone = await screen.findByRole('region', { name: 'For everyone' })
    const subscribers = screen.getByRole('region', { name: 'Subscribers' })
    const vips = screen.getByRole('region', { name: 'VIPs' })

    expect(everyone).toHaveTextContent('!help')
    expect(everyone).not.toHaveTextContent('!sub-only')
    expect(subscribers).toHaveTextContent('!sub-only')
    expect(vips).toHaveTextContent('!vip-only')
    expect(screen.queryByText('Mod')).not.toBeInTheDocument()
    expect(screen.queryByText('Broadcaster')).not.toBeInTheDocument()
  })
})
