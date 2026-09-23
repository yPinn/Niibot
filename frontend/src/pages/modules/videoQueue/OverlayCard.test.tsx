import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { OverlayCard } from './OverlayCard'

const URL =
  'https://example.test/streamer/video-queue/overlay#key=11111111-1111-4111-8111-111111111111'

const CURRENT = {
  id: 7,
  video_id: 'dQw4w9WgXcQ',
  title: 'Current video',
  duration_seconds: 120,
  is_vertical: false,
  start_seconds: 0,
  requested_by: 'viewer',
  source: 'chat' as const,
  video_type: 'youtube' as const,
  started_at: null,
}

describe('OverlayCard capability controls', () => {
  it('keeps the capability fragment after the preview query', async () => {
    render(<OverlayCard url={URL} current={null} onOpenGuide={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '載入同步預覽' }))

    expect(screen.getByTitle('Overlay 預覽')).toHaveAttribute(
      'src',
      'https://example.test/streamer/video-queue/overlay?preview=1#key=11111111-1111-4111-8111-111111111111'
    )
    expect(screen.getByText('跟隨正式 Overlay · 靜音 · 唯讀')).toBeInTheDocument()
  })

  it('confirms before invalidating the current OBS URL', async () => {
    const onRotateUrl = vi.fn()
    render(<OverlayCard url={URL} current={null} onOpenGuide={vi.fn()} onRotateUrl={onRotateUrl} />)

    await userEvent.click(screen.getByRole('button', { name: '重設 OBS 網址' }))
    expect(onRotateUrl).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '重設網址' }))
    expect(onRotateUrl).toHaveBeenCalledOnce()
  })

  it('builds a preview URL after an existing query without requiring a capability fragment', async () => {
    render(
      <OverlayCard
        url="https://example.test/streamer/video-queue/overlay?mode=test"
        current={null}
        onOpenGuide={vi.fn()}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '載入同步預覽' }))

    expect(screen.getByTitle('Overlay 預覽')).toHaveAttribute(
      'src',
      'https://example.test/streamer/video-queue/overlay?mode=test&preview=1'
    )
  })

  it('shows the current poster context and a disabled icon while saving', () => {
    const { container } = render(
      <OverlayCard
        url={URL}
        current={CURRENT}
        onSaveOutput={vi.fn()}
        saving
        onOpenGuide={vi.fn()}
      />
    )

    expect(screen.getByText('跟隨目前項目；嵌入備援可能從頭開始')).toBeInTheDocument()
    expect(container.querySelector('img[alt=""]')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '儲存播放設定' })).toBeDisabled()
  })

  it('edits and saves the normalized overlay volume', async () => {
    const onVolumeChange = vi.fn()
    const onSaveOutput = vi.fn()
    render(
      <OverlayCard
        url={URL}
        current={null}
        volumePercent="35"
        onVolumeChange={onVolumeChange}
        onSaveOutput={onSaveOutput}
        onOpenGuide={vi.fn()}
      />
    )

    const input = screen.getByRole('spinbutton', { name: '播放器音量' })
    expect(input).toHaveValue(35)
    expect(input).toHaveAttribute('inputmode', 'numeric')
    expect(input).toHaveAttribute('min', '0')
    expect(input).toHaveAttribute('max', '100')
    expect(input).toHaveClass(
      '[appearance:textfield]',
      '[&::-webkit-inner-spin-button]:appearance-none',
      '[&::-webkit-outer-spin-button]:appearance-none'
    )
    fireEvent.change(input, { target: { value: '60' } })
    expect(onVolumeChange).toHaveBeenLastCalledWith('60')
    const save = screen.getByRole('button', { name: '儲存播放設定' })
    expect(save).toHaveClass('size-9')
    expect(save).not.toHaveTextContent('儲存播放設定')
    expect(save.parentElement).toHaveClass('sm:shrink-0')
    await userEvent.click(save)
    expect(onSaveOutput).toHaveBeenCalledOnce()
  })
})
