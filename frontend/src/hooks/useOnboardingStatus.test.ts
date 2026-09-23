import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

const capabilityMocks = vi.hoisted(() => ({
  isAvailable: vi.fn(() => true),
}))

import type { ModStatusResult } from '@/api/channels'
import { getBotModStatus } from '@/api/channels'
import type { CommandConfig } from '@/api/commands'
import { getCommandConfigs } from '@/api/commands'
import type { EventConfig } from '@/api/events'
import { getEventConfigs } from '@/api/events'
import type { TimerConfig } from '@/api/timers'
import { getTimerConfigs } from '@/api/timers'
import { getTriggerConfigs } from '@/api/triggers'
import { useAuth } from '@/contexts/AuthContext'
import { useOnboardingStatus } from '@/hooks/useOnboardingStatus'

vi.mock('@/api/channels')
vi.mock('@/api/commands')
vi.mock('@/api/triggers')
vi.mock('@/api/events')
vi.mock('@/api/timers')
vi.mock('@/contexts/AuthContext')
vi.mock('@/hooks/useTwitchCapabilities', () => ({
  useTwitchCapabilities: () => ({
    loading: false,
    error: false,
    snapshot: null,
    capability: vi.fn(),
    refresh: vi.fn(),
    ...capabilityMocks,
  }),
}))

const mockUseAuth = useAuth as MockedFunction<typeof useAuth>
const mockGetBotModStatus = getBotModStatus as MockedFunction<typeof getBotModStatus>
const mockGetCommandConfigs = getCommandConfigs as MockedFunction<typeof getCommandConfigs>
const mockGetTriggerConfigs = getTriggerConfigs as MockedFunction<typeof getTriggerConfigs>
const mockGetEventConfigs = getEventConfigs as MockedFunction<typeof getEventConfigs>
const mockGetTimerConfigs = getTimerConfigs as MockedFunction<typeof getTimerConfigs>

function authValue(
  overrides: Partial<ReturnType<typeof useAuth>> = {}
): ReturnType<typeof useAuth> {
  return {
    user: { id: 'u1' } as ReturnType<typeof useAuth>['user'],
    isAuthenticated: true,
    isInitialized: true,
    isInitError: false,
    isAffiliate: true,
    channels: [],
    logout: vi.fn(),
    refreshUser: vi.fn(),
    refreshChannels: vi.fn(),
    retryInit: vi.fn(),
    ...overrides,
  }
}

const OK_MOD: ModStatusResult = { ok: true, data: { is_moderator: true } }
const CUSTOM_COMMAND: CommandConfig = {
  id: 1,
  channel_id: 'c1',
  command_name: '!x',
  command_type: 'custom',
  enabled: true,
  custom_response: 'hi',
  cooldown: null,
  min_role: 'everyone',
  aliases: null,
  usage_count: 0,
  description: '',
}
const ENABLED_EVENT: EventConfig = {
  id: 1,
  channel_id: 'c1',
  event_type: 'follow',
  message_template: 'welcome',
  enabled: true,
  options: {},
  trigger_count: 0,
}
const CUSTOM_TIMER: TimerConfig = {
  id: 1,
  channel_id: 'c1',
  timer_name: 'promo',
  interval_seconds: 600,
  min_lines: 0,
  message_template: 'hi',
  enabled: true,
  announce: false,
  command_alias: null,
  builtin: false,
  created_at: null,
  updated_at: null,
}

describe('useOnboardingStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capabilityMocks.isAvailable.mockReturnValue(true)
  })

  it('aggregates every source as done when everything is set up', async () => {
    mockUseAuth.mockReturnValue(authValue())
    mockGetBotModStatus.mockResolvedValue(OK_MOD)
    mockGetCommandConfigs.mockResolvedValue([CUSTOM_COMMAND])
    mockGetTriggerConfigs.mockResolvedValue([])
    mockGetEventConfigs.mockResolvedValue([ENABLED_EVENT])
    mockGetTimerConfigs.mockResolvedValue([CUSTOM_TIMER])

    const { result } = renderHook(() => useOnboardingStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.status).toEqual({
      modDone: true,
      commandsDone: true,
      eventsDone: true,
      timersDone: true,
    })
  })

  it('reports eventsDone as null and never calls the events API for a non-affiliate', async () => {
    mockUseAuth.mockReturnValue(authValue({ isAffiliate: false }))
    mockGetBotModStatus.mockResolvedValue(OK_MOD)
    mockGetCommandConfigs.mockResolvedValue([])
    mockGetTriggerConfigs.mockResolvedValue([])
    mockGetTimerConfigs.mockResolvedValue([])

    const { result } = renderHook(() => useOnboardingStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.status.eventsDone).toBeNull()
    expect(mockGetEventConfigs).not.toHaveBeenCalled()
  })

  it('leaves only the failed source null without affecting the others', async () => {
    mockUseAuth.mockReturnValue(authValue())
    mockGetBotModStatus.mockRejectedValue(new Error('network error'))
    mockGetCommandConfigs.mockResolvedValue([CUSTOM_COMMAND])
    mockGetTriggerConfigs.mockResolvedValue([])
    mockGetEventConfigs.mockResolvedValue([ENABLED_EVENT])
    mockGetTimerConfigs.mockResolvedValue([CUSTOM_TIMER])

    const { result } = renderHook(() => useOnboardingStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.status).toEqual({
      modDone: null,
      commandsDone: true,
      eventsDone: true,
      timersDone: true,
    })
  })

  it('does not fetch anything when there is no user', () => {
    mockUseAuth.mockReturnValue(authValue({ user: null }))

    renderHook(() => useOnboardingStatus())

    expect(mockGetBotModStatus).not.toHaveBeenCalled()
    expect(mockGetCommandConfigs).not.toHaveBeenCalled()
    expect(mockGetTriggerConfigs).not.toHaveBeenCalled()
    expect(mockGetEventConfigs).not.toHaveBeenCalled()
    expect(mockGetTimerConfigs).not.toHaveBeenCalled()
  })

  it('does not probe MOD relation when the optional MOD scope is locked', async () => {
    mockUseAuth.mockReturnValue(authValue())
    capabilityMocks.isAvailable.mockReturnValue(false)
    mockGetCommandConfigs.mockResolvedValue([])
    mockGetTriggerConfigs.mockResolvedValue([])
    mockGetEventConfigs.mockResolvedValue([])
    mockGetTimerConfigs.mockResolvedValue([])

    const { result } = renderHook(() => useOnboardingStatus())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.status.modDone).toBeNull()
    expect(mockGetBotModStatus).not.toHaveBeenCalled()
  })
})
