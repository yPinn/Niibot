import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CommandConfig } from '@/api/commands'

import { CommandSheet } from './CommandSheet'

const SUBAGE: CommandConfig = {
  id: null,
  channel_id: 'channel-1',
  command_name: 'subage',
  command_type: 'builtin',
  enabled: true,
  custom_response: null,
  cooldown: 15,
  min_role: 'everyone',
  aliases: '訂閱資訊',
  usage_count: 10,
  description: '查詢自己的累積訂閱月數',
  detail: '回覆觸發者目前的累積訂閱月數、訂閱 Tier，以及是否為禮物訂閱。',
  usage: '!subage',
  preview_input: '!subage',
  preview_output: '@小霓 累積訂閱 14 個月，目前是 T2 訂閱者',
  audience: 'viewer',
  public_visible: true,
  display_order: 5,
  category_label: '觀眾查詢',
}

describe('CommandSheet', () => {
  it('offers every canonical argument and URL conversion variable', () => {
    render(
      <CommandSheet
        open
        editing={{ mode: 'create' }}
        defaults={{ default_cooldown: 0 }}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '$(1:)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '$(1|預設值)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '$(queryescape)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '$(pathescape)' })).toBeInTheDocument()
  })

  it('explains builtin behavior, audience, usage, and public visibility before settings', () => {
    render(
      <CommandSheet
        open
        editing={{ mode: 'edit-command', command: SUBAGE }}
        defaults={{ default_cooldown: 0 }}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('heading', { name: '編輯 !subage' })).toBeInTheDocument()
    const feature = screen.getByRole('region', { name: '指令功能' })
    expect(feature).toHaveTextContent('累積訂閱月數、訂閱 Tier')
    expect(feature).toHaveTextContent('!subage')
    expect(feature).toHaveTextContent('觀眾')
    expect(feature).toHaveTextContent('For everyone')
    expect(feature).toHaveTextContent('顯示於公開指令頁')
    expect(feature).toHaveTextContent('效果預覽')
    expect(feature).toHaveTextContent('!subage')
    expect(feature).toHaveTextContent('@小霓 累積訂閱 14 個月，目前是 T2 訂閱者')
    expect(feature).toHaveTextContent('示意內容，不會實際執行指令')
  })
})
