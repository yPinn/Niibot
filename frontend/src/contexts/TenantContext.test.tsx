import type React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/tenants', () => ({ getTenants: vi.fn() }))
vi.mock('@/contexts/AuthContext', () => ({ useAuth: vi.fn() }))

import { getTenants } from '@/api/tenants'
import { useAuth } from '@/contexts/AuthContext'
import { TenantProvider, useTenant } from '@/contexts/TenantContext'

const mockGetTenants = vi.mocked(getTenants)
const mockUseAuth = vi.mocked(useAuth)

const TENANTS = [
  {
    channel_id: 'channel-a',
    channel_name: 'alice',
    display_name: 'Alice',
    enabled: true,
    role: 'owner' as const,
    capabilities: ['edit_operations', 'switch_bot', 'toggle_bot'] as const,
  },
  {
    channel_id: 'channel-b',
    channel_name: 'bob',
    display_name: 'Bob',
    enabled: true,
    role: 'manager' as const,
    capabilities: ['edit_operations'] as const,
  },
]

function wrapper({ children }: { children: React.ReactNode }) {
  return <TenantProvider>{children}</TenantProvider>
}

describe('TenantProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({
      user: { id: 'u1' },
      isAuthenticated: true,
      isInitialized: true,
    } as ReturnType<typeof useAuth>)
    mockGetTenants.mockResolvedValue(TENANTS.map(tenant => ({ ...tenant })))
  })

  it('loads accessible tenants independently from monitored channels', async () => {
    const { result } = renderHook(() => useTenant(), { wrapper })

    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    expect(result.current.tenants).toHaveLength(2)
    expect(result.current.activeTenant?.channel_id).toBe('channel-a')
    expect(mockGetTenants).toHaveBeenCalledWith({ forceRefresh: true })
  })

  it('switches only to a server-returned tenant', async () => {
    const { result } = renderHook(() => useTenant(), { wrapper })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    act(() => result.current.selectTenant('channel-b'))
    expect(result.current.activeTenant?.channel_id).toBe('channel-b')

    act(() => result.current.selectTenant('unknown'))
    expect(result.current.activeTenant?.channel_id).toBe('channel-b')
  })

  it('does not fetch before authentication is initialized', async () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isInitialized: false,
    } as ReturnType<typeof useAuth>)

    const { result } = renderHook(() => useTenant(), { wrapper })

    expect(result.current.isInitialized).toBe(false)
    expect(mockGetTenants).not.toHaveBeenCalled()
  })
})
