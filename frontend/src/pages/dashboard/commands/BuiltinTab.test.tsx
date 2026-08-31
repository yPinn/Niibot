import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CommandConfig } from '@/api/commands'
import { useSortState } from '@/hooks/useSortState'

import { BuiltinTab } from './BuiltinTab'
import type { SortKey } from './types'

function command(
  commandName: string,
  categoryLabel: string,
  displayOrder: number,
  minRole = 'everyone'
): CommandConfig {
  return {
    id: null,
    channel_id: 'channel-1',
    command_name: commandName,
    command_type: 'builtin',
    enabled: true,
    custom_response: null,
    cooldown: 5,
    min_role: minRole,
    aliases: null,
    usage_count: 0,
    description: commandName,
    detail: `${commandName} detail`,
    usage: `!${commandName}`,
    preview_input: `!${commandName}`,
    preview_output: `${commandName} preview`,
    audience: minRole === 'moderator' ? 'moderator' : 'viewer',
    public_visible: minRole !== 'moderator',
    display_order: displayOrder,
    category_label: categoryLabel,
  }
}

function Subject({ commands }: { commands: CommandConfig[] }) {
  const sortState = useSortState<SortKey>('catalog_order')
  return (
    <BuiltinTab
      commands={commands}
      sortState={sortState}
      defaults={{ default_cooldown: 0 }}
      onToggle={vi.fn()}
      onEdit={vi.fn()}
    />
  )
}

describe('BuiltinTab', () => {
  it('preserves catalog frequency order and uses Twitch role names', () => {
    render(
      <Subject
        commands={[
          command('help', '常用互動', 0),
          command('checkin', '常用互動', 1),
          command('subage', '觀眾查詢', 2),
          command('subcount', '實況主工具', 3, 'broadcaster'),
          command('so', 'Mod 工具', 4, 'moderator'),
        ]}
      />
    )

    const table = screen.getByRole('table')
    const content = table.textContent ?? ''
    expect(content.indexOf('!help')).toBeLessThan(content.indexOf('!checkin'))
    expect(content.indexOf('常用互動')).toBeLessThan(content.indexOf('觀眾查詢'))
    expect(content.indexOf('觀眾查詢')).toBeLessThan(content.indexOf('實況主工具'))
    expect(content.indexOf('實況主工具')).toBeLessThan(content.indexOf('Mod 工具'))

    const modRow = screen.getByRole('row', { name: /!so/ })
    expect(within(modRow).getByText('Mod')).toBeInTheDocument()
  })
})
