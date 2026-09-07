import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SecretInput } from './SecretInput'

describe('SecretInput', () => {
  it('renders the label bound to the input', () => {
    render(
      <SecretInput
        label="HashKey"
        value=""
        onChange={vi.fn()}
        revealed={false}
        onToggleReveal={vi.fn()}
      />
    )
    expect(screen.getByLabelText('HashKey')).toBeInTheDocument()
  })

  it('masks the value until revealed', () => {
    const { rerender } = render(
      <SecretInput
        label="HashKey"
        value="secret"
        onChange={vi.fn()}
        revealed={false}
        onToggleReveal={vi.fn()}
      />
    )
    expect(screen.getByLabelText('HashKey')).toHaveAttribute('type', 'password')

    rerender(
      <SecretInput
        label="HashKey"
        value="secret"
        onChange={vi.fn()}
        revealed
        onToggleReveal={vi.fn()}
      />
    )
    expect(screen.getByLabelText('HashKey')).toHaveAttribute('type', 'text')
  })

  it('reports typed characters through onChange', async () => {
    const onChange = vi.fn()
    render(
      <SecretInput label="HashKey" value="" onChange={onChange} revealed onToggleReveal={vi.fn()} />
    )
    await userEvent.type(screen.getByLabelText('HashKey'), 'ab')
    expect(onChange).toHaveBeenLastCalledWith('b')
  })

  it('calls onToggleReveal when the eye button is clicked', async () => {
    const onToggleReveal = vi.fn()
    render(
      <SecretInput
        label="HashKey"
        value=""
        onChange={vi.fn()}
        revealed={false}
        onToggleReveal={onToggleReveal}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '顯示金鑰' }))
    expect(onToggleReveal).toHaveBeenCalledOnce()
  })
})
