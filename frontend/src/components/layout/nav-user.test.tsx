import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { User } from '@/api'
import { NavUser } from '@/components/layout/nav-user'
import { SidebarProvider } from '@/components/ui'
import { useTenant } from '@/contexts/TenantContext'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ logout: vi.fn() }),
}))
vi.mock('@/components/layout/theme-provider', () => ({
  useTheme: () => ({ resolvedTheme: 'dark', setTheme: vi.fn() }),
}))
vi.mock('@/contexts/TenantContext')

const mockUseTenant = vi.mocked(useTenant)
const selectTenant = vi.fn()
const user: User = {
  id: 'u1',
  name: 'moderator',
  display_name: 'Moderator',
  avatar: '',
  platform: 'twitch',
  theme: 'dark',
  broadcaster_type: '',
  is_activated: true,
  is_owner: false,
}

function renderUser(showWorkspaces = true) {
  return render(
    <MemoryRouter initialEntries={['/dashboard/channel-a/events']}>
      <SidebarProvider>
        <NavUser user={user} showWorkspaces={showWorkspaces} />
      </SidebarProvider>
    </MemoryRouter>
  )
}

describe('NavUser workspace hub', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
    mockUseTenant.mockReturnValue({
      tenants: [
        {
          channel_id: 'channel-a',
          channel_name: 'alice',
          display_name: 'Alice',
          enabled: true,
          role: 'owner',
          capabilities: ['edit_operations'],
        },
        {
          channel_id: 'channel-b',
          channel_name: 'bob',
          display_name: 'Bob',
          enabled: true,
          role: 'manager',
          capabilities: ['edit_operations'],
        },
      ],
      activeTenant: {
        channel_id: 'channel-a',
        channel_name: 'alice',
        display_name: 'Alice',
        enabled: true,
        role: 'owner',
        capabilities: ['edit_operations'],
      },
      isInitialized: true,
      isLoading: false,
      error: null,
      refreshTenants: vi.fn(),
      selectTenant,
    })
  })

  it('shows the active workspace and the signed-in identity together', () => {
    renderUser()

    const workspaceName = screen.getByText('Alice')
    const roleBadge = screen.getByRole('img', { name: '擁有者' })

    expect(roleBadge.compareDocumentPosition(workspaceName)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(workspaceName.parentElement).toHaveClass('items-center', 'text-sm', 'leading-[18px]')
    expect(roleBadge).toHaveAttribute('width', '18')
    expect(roleBadge).toHaveAttribute('height', '18')
    expect(screen.getByText('@moderator')).toBeInTheDocument()
  })

  it('reveals workspace choices in the account menu', async () => {
    renderUser()

    fireEvent.pointerDown(screen.getByRole('button'), { button: 0, ctrlKey: false })

    expect(await screen.findByText('登入身分')).toBeInTheDocument()
    expect(screen.getByText('切換工作區')).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /擁有者Alice/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /ModBob/ })).toBeInTheDocument()
  })

  it('falls back to the signed-in identity outside Twitch workspaces', () => {
    renderUser(false)

    expect(screen.getByText('Moderator')).toBeInTheDocument()
    expect(screen.getByText('@moderator')).toBeInTheDocument()
  })
})
