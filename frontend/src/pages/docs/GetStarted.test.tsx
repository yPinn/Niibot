import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/hooks/useGrantMod', () => ({
  useGrantMod: () => ({ granting: false, grantMod: vi.fn() }),
}))
vi.mock('@/hooks/useOnboardingStatus', () => ({
  useOnboardingStatus: () => ({
    loading: false,
    status: { modDone: false, commandsDone: null, eventsDone: null, timersDone: null },
  }),
}))
vi.mock('@/components/DiscordHelpBanner', () => ({ DiscordHelpBanner: () => null }))

import { BOT_USERNAME } from '@/api/config'

import GetStarted from './GetStarted'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <GetStarted />
    </MemoryRouter>
  )
}

describe('GetStarted mod setup', () => {
  it('keeps the manual steps collapsed behind the one-click grant', () => {
    renderAt('/docs/get-started')

    expect(screen.getByRole('button', { name: '一鍵授予 Mod' })).toBeInTheDocument()
    expect(screen.queryByText('聊天室指令')).not.toBeInTheDocument()
  })

  it('opens the manual steps when arriving from the Overview prompt', () => {
    renderAt('/docs/get-started#manual-mod')

    expect(screen.getByText('聊天室指令')).toBeInTheDocument()
    expect(screen.getAllByText(`/mod ${BOT_USERNAME}`).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '複製指令' })).toBeInTheDocument()
  })
})
