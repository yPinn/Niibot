import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const mockUseAuth = vi.fn()
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

import { SetupGuideSheet } from './SetupGuideSheet'

describe('SetupGuideSheet', () => {
  it('walks through Twitch reward creation, Niibot binding, and OBS setup with working CTAs', async () => {
    mockUseAuth.mockReturnValue({ user: { name: 'llazypilot' } })
    const onOpenChange = vi.fn()
    render(
      <MemoryRouter>
        <SetupGuideSheet open onOpenChange={onOpenChange} />
      </MemoryRouter>
    )

    expect(screen.getByText('在 Twitch 建立獎勵')).toBeInTheDocument()
    expect(screen.getByText('在 Niibot 綁定獎勵')).toBeInTheDocument()
    expect(screen.getByText('OBS 加入畫面')).toBeInTheDocument()

    // step 2 must name the real page ("Channel Points"), not the stale "Events" flow
    expect(screen.getByText('開放用頻道點數兌換')).toBeInTheDocument()

    // Twitch CTA deep-links straight to this user's rewards page
    const twitchCta = screen.getByRole('link', { name: /前往 Twitch 獎勵頁面/ })
    expect(twitchCta).toHaveAttribute(
      'href',
      'https://dashboard.twitch.tv/u/llazypilot/viewer-rewards/channel-points/rewards'
    )
    expect(twitchCta).toHaveAttribute('target', '_blank')

    const channelPointsCta = screen.getByRole('link', { name: /前往 Channel Points 頁面/ })
    expect(channelPointsCta).toHaveAttribute('href', '/channel-points')

    await userEvent.click(channelPointsCta)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('falls back to the generic Twitch dashboard URL when the username is unavailable', () => {
    mockUseAuth.mockReturnValue({ user: undefined })
    render(
      <MemoryRouter>
        <SetupGuideSheet open onOpenChange={vi.fn()} />
      </MemoryRouter>
    )

    expect(screen.getByRole('link', { name: /前往 Twitch 獎勵頁面/ })).toHaveAttribute(
      'href',
      'https://dashboard.twitch.tv/'
    )
  })
})
