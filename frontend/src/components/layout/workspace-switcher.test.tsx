import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceSwitcher } from '@/components/layout/workspace-switcher'
import { useTenant } from '@/contexts/TenantContext'

vi.mock('@/contexts/TenantContext')

const mockUseTenant = vi.mocked(useTenant)
const selectTenant = vi.fn()

describe('WorkspaceSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

  it('shows only server-returned workspaces and their lightweight roles', () => {
    render(
      <MemoryRouter>
        <WorkspaceSwitcher />
      </MemoryRouter>
    )

    expect(screen.getByRole('option', { name: 'Alice（擁有者）' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Bob（MOD）' })).toBeInTheDocument()
  })

  it('selects the workspace and navigates to its channel-scoped dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard/channel-a']}>
        <WorkspaceSwitcher />
      </MemoryRouter>
    )

    fireEvent.change(screen.getByRole('combobox', { name: '目前工作區' }), {
      target: { value: 'channel-b' },
    })

    expect(selectTenant).toHaveBeenCalledWith('channel-b')
  })
})
