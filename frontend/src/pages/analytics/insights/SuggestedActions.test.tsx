import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Suggestion } from '@/lib/insights-suggestions'

import { SuggestedActions } from './SuggestedActions'

const SUGGESTIONS: Suggestion[] = [
  { id: 'churn-risk', tone: 'warning', icon: 'fa-solid fa-user-clock', text: '3 位常客最近沒回來' },
  { id: 'sub-conversion', tone: 'action', icon: 'fa-solid fa-star', text: '訂閱轉換率偏低' },
  {
    id: 'core-stable',
    tone: 'positive',
    icon: 'fa-solid fa-heart-circle-check',
    text: '核心觀眾穩定',
  },
]

describe('SuggestedActions', () => {
  it('renders nothing when there are no suggestions', () => {
    const { container } = render(<SuggestedActions suggestions={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the section title and one row per suggestion', () => {
    render(<SuggestedActions suggestions={SUGGESTIONS} />)
    expect(screen.getByText('建議行動')).toBeInTheDocument()
    for (const s of SUGGESTIONS) {
      expect(screen.getByText(s.text)).toBeInTheDocument()
    }
  })

  it('applies the tone-specific color class to each row icon', () => {
    render(<SuggestedActions suggestions={SUGGESTIONS} />)
    const warningIcon = screen.getByText('3 位常客最近沒回來').previousElementSibling
    const actionIcon = screen.getByText('訂閱轉換率偏低').previousElementSibling
    const positiveIcon = screen.getByText('核心觀眾穩定').previousElementSibling
    expect(warningIcon).toHaveClass('text-status-warning')
    expect(actionIcon).toHaveClass('text-status-info')
    expect(positiveIcon).toHaveClass('text-status-success')
  })
})
