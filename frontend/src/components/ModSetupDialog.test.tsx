import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/hooks/useGrantMod', () => ({
  useGrantMod: () => ({ granting: false, grantMod: vi.fn() }),
}))

import { isModPromptDismissed } from '@/lib/mod-prompt'

import { ModSetupDialog } from './ModSetupDialog'

function renderDialog(onOpenChange = vi.fn()) {
  render(
    <MemoryRouter>
      <ModSetupDialog open onOpenChange={onOpenChange} />
    </MemoryRouter>
  )
  return onOpenChange
}

describe('ModSetupDialog', () => {
  beforeEach(() => sessionStorage.clear())

  it('uses the same wording as the Get Started mod card', () => {
    renderDialog()

    expect(screen.getByRole('dialog', { name: '讓 Niibot 成為管理員' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '一鍵授予 Mod' })).toBeInTheDocument()
  })

  it('remembers "later" for the session so Overview stops re-prompting', async () => {
    const user = userEvent.setup()
    const onOpenChange = renderDialog()

    await user.click(screen.getByRole('button', { name: '稍後再說' }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(isModPromptDismissed()).toBe(true)
  })

  it('sends manual setup straight to the expanded steps on Get Started', () => {
    renderDialog()

    expect(screen.getByRole('link', { name: '手動設定' })).toHaveAttribute(
      'href',
      '/docs/get-started#manual-mod'
    )
  })
})
