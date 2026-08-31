import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEFAULT_COMMUNITY_OVERLAY_THEME } from '@/api/communityOverlay'

import { TarotCard } from './TarotCard'

const EVENT = {
  actor_display_name: 'Alice',
  payload: {
    card_id: '0',
    card_name: '愚者',
    card_name_en: 'The Fool',
    orientation: 'upright' as const,
    orientation_label: '正位',
    category: 'general',
    category_label: '綜合',
    keywords: ['新開始', '冒險', '自由', '第四個不應顯示'],
    meaning: '進入全新階段，無限可能展開。',
    advice: '保持開放心態，相信你的第一步。',
    image_path: '/images/tarot/decks/rider-waite-smith-pkt/v1/cards/major-00-the-fool.jpg',
    deck_id: 'rider-waite-smith-pkt',
    deck_version: 1,
  },
}

describe('TarotCard', () => {
  it('renders a card-only reveal surface with a scripted virtual cursor', () => {
    render(<TarotCard event={EVENT} theme={DEFAULT_COMMUNITY_OVERLAY_THEME} />)

    expect(screen.getByLabelText('Alice 的每日塔羅：愚者正位')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '愚者正位' })).toHaveAttribute(
      'src',
      EVENT.payload.image_path
    )
    expect(screen.getByTestId('tarot-card-back')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByTestId('tarot-hologram')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByTestId('tarot-reveal')).toHaveAttribute('data-virtual-pointer', 'scripted')
    expect(screen.queryByText('@Alice')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.queryByText('愚者')).not.toBeInTheDocument()
    expect(screen.queryByText('正位')).not.toBeInTheDocument()
    expect(screen.queryByText('The Fool')).not.toBeInTheDocument()
    expect(screen.queryByText('新開始')).not.toBeInTheDocument()
    expect(screen.queryByText('第四個不應顯示')).not.toBeInTheDocument()
    expect(screen.queryByText(EVENT.payload.meaning)).not.toBeInTheDocument()
    expect(screen.queryByText(EVENT.payload.advice)).not.toBeInTheDocument()
  })

  it('marks reversed artwork and preview state without changing the image path', () => {
    render(
      <TarotCard
        event={{
          ...EVENT,
          payload: {
            ...EVENT.payload,
            orientation: 'reversed',
            orientation_label: '逆位',
            preview: true,
          },
        }}
        theme={DEFAULT_COMMUNITY_OVERLAY_THEME}
      />
    )

    expect(screen.getByTestId('tarot-artwork')).toHaveAttribute('data-orientation', 'reversed')
    expect(screen.getByText('PREVIEW')).toBeInTheDocument()
  })

  it('shows the final face without virtual cursor motion when animation is disabled', () => {
    render(
      <TarotCard event={EVENT} theme={{ ...DEFAULT_COMMUNITY_OVERLAY_THEME, motion: 'none' }} />
    )

    expect(screen.getByTestId('tarot-reveal')).toHaveAttribute('data-virtual-pointer', 'off')
    expect(screen.getByTestId('tarot-flipper')).toHaveAttribute('data-reveal-state', 'face')
  })
})
