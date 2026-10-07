import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { copyToClipboard } from '@/lib/clipboard'

import { obsDropUrl, OverlayUrlBlock } from './OverlayUrlBlock'

vi.mock('@/lib/clipboard', () => ({ copyToClipboard: vi.fn() }))

const URL = 'https://niibot.example/streamer/video-queue/overlay#key=abc'

describe('obsDropUrl', () => {
  it('adds the OBS layer params before the capability fragment', () => {
    expect(obsDropUrl(URL, { name: 'Niibot Video Queue', width: 640, height: 400 })).toBe(
      'https://niibot.example/streamer/video-queue/overlay' +
        '?layer-name=Niibot%20Video%20Queue&layer-width=640&layer-height=400#key=abc'
    )
  })

  it('encodes spaces as %20, never `+` (OBS shows a `+` literally)', () => {
    expect(obsDropUrl('https://x.example/o', { name: 'A B' })).not.toContain('+')
  })

  it('appends to an existing query and omits an unknown size', () => {
    expect(obsDropUrl('https://x.example/o?theme=dark', { name: 'Q' })).toBe(
      'https://x.example/o?theme=dark&layer-name=Q'
    )
  })
})

describe('OverlayUrlBlock', () => {
  it('copies on click and keeps the hint unselectable', async () => {
    render(<OverlayUrlBlock url={URL} />)
    const block = screen.getByRole('button', { name: /點擊複製 OBS 網址/ })
    expect(block).toHaveClass('select-none')
    await userEvent.click(block)
    expect(copyToClipboard).toHaveBeenCalledWith(URL, '已複製', '複製失敗，請手動選取網址')
  })

  it('lets a revealed URL be selected by hand (the copy-failure fallback)', async () => {
    const { container } = render(<OverlayUrlBlock url={URL} />)
    await userEvent.click(screen.getByRole('button', { name: '顯示網址' }))
    expect(container.querySelector('code')).toHaveClass('select-text')
  })

  it('drags a pre-named, pre-sized URL into OBS without copying', () => {
    vi.mocked(copyToClipboard).mockClear()
    render(<OverlayUrlBlock url={URL} obsSource={{ name: 'Q', width: 640, height: 400 }} />)
    const handle = screen.getByLabelText('拖曳到 OBS')
    expect(handle).toHaveAttribute('draggable', 'true')

    const setData = vi.fn()
    fireEvent.dragStart(handle, { dataTransfer: { setData, effectAllowed: '' } })
    const expected =
      'https://niibot.example/streamer/video-queue/overlay?layer-name=Q&layer-width=640&layer-height=400#key=abc'
    expect(setData).toHaveBeenCalledWith('text/uri-list', expected)
    expect(setData).toHaveBeenCalledWith('text/plain', expected)

    fireEvent.click(handle)
    expect(copyToClipboard).not.toHaveBeenCalled()
  })

  it('has no drag handle unless the page opts in', () => {
    render(<OverlayUrlBlock url={URL} />)
    expect(screen.queryByLabelText('拖曳到 OBS')).toBeNull()
  })

  it('resets only after confirming, and only when the page offers it', async () => {
    const onRotate = vi.fn()
    const { rerender } = render(<OverlayUrlBlock url={URL} />)
    expect(screen.queryByRole('button', { name: '重設網址' })).toBeNull()

    rerender(<OverlayUrlBlock url={URL} onRotate={onRotate} />)
    await userEvent.click(screen.getByRole('button', { name: '重設網址' }))
    expect(onRotate).not.toHaveBeenCalled()
    await userEvent.click(
      within(screen.getByRole('alertdialog')).getByRole('button', { name: '重設網址' })
    )
    expect(onRotate).toHaveBeenCalledOnce()
  })

  it('disables reset while a rotation is in flight', () => {
    render(<OverlayUrlBlock url={URL} onRotate={vi.fn()} rotating />)
    expect(screen.getByRole('button', { name: '重設網址' })).toBeDisabled()
  })
})
