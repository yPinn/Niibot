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

    // Set up first (binding needs the Twitch reward), switch on last.
    expect(screen.getAllByRole('heading', { level: 3 }).map(h => h.textContent)).toEqual([
      'OBS 加入畫面',
      '在 Twitch 建立獎勵',
      '綁定獎勵',
      '開啟點播',
    ])

    // step 2 must name the real page ("Channel Points"), not the stale "Events" flow
    expect(screen.getByText('開放忠誠點數點播')).toBeInTheDocument()
    // the suggested reward prompt advertises the segment syntax
    expect(screen.getByText(/可於網址後加上播放片段，例：1:30-4:00/)).toBeInTheDocument()

    // Twitch CTA deep-links straight to this user's rewards page
    const twitchCta = screen.getByRole('link', { name: /^Twitch$/ })
    expect(twitchCta).toHaveAttribute(
      'href',
      'https://dashboard.twitch.tv/u/llazypilot/viewer-rewards/channel-points/rewards'
    )
    expect(twitchCta).toHaveAttribute('target', '_blank')

    const channelPointsCta = screen.getByRole('link', { name: /忠誠點數/ })
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

    expect(screen.getByRole('link', { name: /^Twitch$/ })).toHaveAttribute(
      'href',
      'https://dashboard.twitch.tv/'
    )
  })
})
