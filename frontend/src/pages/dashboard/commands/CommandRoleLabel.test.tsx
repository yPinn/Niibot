import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CommandRoleLabel } from './CommandRoleLabel'

describe('CommandRoleLabel', () => {
  it.each([
    ['subscriber', '訂閱者'],
    ['vip', 'VIP'],
    ['moderator', 'Mod'],
    ['broadcaster', '實況主'],
  ])('renders the Twitch badge before the %s label', (role, label) => {
    const { container } = render(<CommandRoleLabel role={role} />)

    const badge = container.querySelector('img')
    const text = screen.getByText(label)
    expect(badge).not.toBeNull()
    expect(badge!.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(text.parentElement).toHaveClass('shrink-0', 'whitespace-nowrap')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('uses a viewer icon instead of inventing a Twitch badge for everyone', () => {
    render(<CommandRoleLabel role="everyone" />)

    expect(screen.getByText('所有人')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
