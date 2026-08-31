import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { NavChannels } from '@/components/layout/nav-channels'

describe('NavChannels', () => {
  it('does not reserve sidebar space when there are no monitored channels', () => {
    const { container } = render(<NavChannels channels={[]} />)

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText('Channels')).not.toBeInTheDocument()
  })
})
