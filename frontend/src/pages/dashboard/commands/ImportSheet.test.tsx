import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as CommandImportApi from '@/api/commandImport'
import type { ImportPreview } from '@/api/commandImport'

import { ImportSheet } from './ImportSheet'

vi.mock('@/api/commandImport', async importOriginal => {
  const actual = await importOriginal<typeof CommandImportApi>()
  return {
    ...actual,
    getImportSources: vi.fn(),
    previewStreamElements: vi.fn(),
    getImportPreview: vi.fn(),
    applyImport: vi.fn(),
    getNightbotOauthUrl: vi.fn(),
  }
})

const api = await import('@/api/commandImport')

const PREVIEW: ImportPreview = {
  import_id: 'imp-1',
  source: 'streamelements',
  source_channel: 'niistream',
  items: [
    {
      key: 'builtin:followage',
      section: 'builtin',
      status: 'ok',
      source_name: '!followage',
      source_enabled: true,
      notes: ['改為啟用 Niibot 內建的 !followage'],
      command_name: null,
      response: null,
      original_response: null,
      cooldown: null,
      min_role: 'everyone',
      aliases: [],
      pattern: null,
      match_type: 'contains',
      builtin_target: 'followage',
    },
    {
      key: 'cmd:discord',
      section: 'custom',
      status: 'ok',
      source_name: '!discord',
      source_enabled: true,
      notes: [],
      command_name: 'discord',
      response: '加入我們',
      original_response: '加入我們',
      cooldown: 15,
      min_role: 'everyone',
      aliases: [],
      pattern: null,
      match_type: 'contains',
      builtin_target: null,
    },
    {
      key: 'cmd:hug',
      section: 'custom',
      status: 'review',
      source_name: '!hug',
      source_enabled: false,
      notes: ['變數語法已改寫為 Niibot 格式'],
      command_name: 'hug',
      response: '$(touser) 抱了一下',
      original_response: '$(1|$(sender)) 抱了一下',
      cooldown: null,
      min_role: 'everyone',
      aliases: [],
      pattern: null,
      match_type: 'contains',
      builtin_target: null,
    },
    {
      key: 'nope:pb',
      section: 'unsupported',
      status: 'unsupported',
      source_name: '!pb',
      source_enabled: true,
      notes: ['用到 $(customapi) 對外抓取資料，Niibot 不支援'],
      command_name: null,
      response: null,
      original_response: null,
      cooldown: null,
      min_role: 'everyone',
      aliases: [],
      pattern: null,
      match_type: 'contains',
      builtin_target: null,
    },
  ],
  // The backend preselects importable rows and leaves every one switched off.
  default_selection: {
    'builtin:followage': false,
    'cmd:discord': false,
    'cmd:hug': false,
  },
}

function renderSheet(props: Partial<Parameters<typeof ImportSheet>[0]> = {}) {
  const onImported = vi.fn()
  const onClose = vi.fn()
  render(<ImportSheet open onImported={onImported} onClose={onClose} {...props} />)
  return { onImported, onClose }
}

async function openPreview() {
  const user = userEvent.setup()
  renderSheet()
  await user.click(await screen.findByText('StreamElements'))
  await screen.findByText('新增為自訂指令')
  return user
}

beforeEach(() => {
  vi.mocked(api.getImportSources).mockResolvedValue([
    { source: 'streamelements', available: true, reason: null },
    { source: 'nightbot', available: false, reason: '尚未設定金鑰' },
  ])
  vi.mocked(api.previewStreamElements).mockResolvedValue(PREVIEW)
  vi.mocked(api.getImportPreview).mockResolvedValue(PREVIEW)
  vi.mocked(api.applyImport).mockResolvedValue({
    created: 3,
    enabled: 0,
    skipped: 1,
    failed: 0,
    errors: [],
  })
})

describe('ImportSheet source picker', () => {
  it('offers StreamElements without authorization', async () => {
    renderSheet()
    expect(await screen.findByText('直接讀取，不需要額外授權')).toBeInTheDocument()
  })

  it('disables Nightbot and explains why when it is not configured', async () => {
    renderSheet()
    const nightbot = await screen.findByRole('button', { name: /Nightbot/ })
    expect(nightbot).toBeDisabled()
    expect(nightbot).toHaveTextContent('尚未設定金鑰')
  })
})

describe('ImportSheet preview', () => {
  it('groups rows into sections so platform features are visible, not hidden', async () => {
    await openPreview()
    expect(screen.getByText('對應到內建指令')).toBeInTheDocument()
    expect(screen.getByText('新增為自訂指令')).toBeInTheDocument()
    expect(screen.getByText('無法匯入')).toBeInTheDocument()
  })

  it('preselects importable rows and leaves unsupported ones out', async () => {
    await openPreview()
    expect(screen.getByRole('checkbox', { name: '選取 !discord' })).toHaveAttribute(
      'aria-checked',
      'true'
    )
    const unsupported = screen.getByRole('checkbox', { name: '選取 !pb' })
    expect(unsupported).toHaveAttribute('aria-checked', 'false')
    expect(unsupported).toBeDisabled()
  })

  it('opens with everything switched off', async () => {
    await openPreview()
    for (const name of ['!followage', '!discord', '!hug']) {
      expect(screen.getByRole('switch', { name: `匯入後啟用 ${name}` })).not.toBeChecked()
    }
  })

  it('shows the rewritten response alongside the original', async () => {
    await openPreview()
    expect(screen.getByText('$(touser) 抱了一下')).toBeInTheDocument()
    expect(screen.getByText('$(1|$(sender)) 抱了一下')).toBeInTheDocument()
  })

  it('explains why an unsupported row cannot come across', async () => {
    await openPreview()
    expect(screen.getByText(/用到 \$\(customapi\)/)).toBeInTheDocument()
  })

  it('"沿用原本" restores each row to its state on the old bot', async () => {
    const user = await openPreview()
    await user.click(screen.getByRole('button', { name: '沿用原本' }))
    expect(screen.getByRole('switch', { name: '匯入後啟用 !discord' })).toBeChecked()
    expect(screen.getByRole('switch', { name: '匯入後啟用 !hug' })).not.toBeChecked()
  })

  it('"全部啟用" turns every selected row on', async () => {
    const user = await openPreview()
    await user.click(screen.getByRole('button', { name: '全部啟用' }))
    expect(screen.getByRole('switch', { name: '匯入後啟用 !hug' })).toBeChecked()
  })

  it('unticking a row removes it from the count', async () => {
    const user = await openPreview()
    expect(screen.getByRole('button', { name: /匯入勾選的 3 筆/ })).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: '選取 !discord' }))
    expect(screen.getByRole('button', { name: /匯入勾選的 2 筆/ })).toBeInTheDocument()
  })
})

describe('ImportSheet apply', () => {
  it('sends only the ticked rows with their enabled state', async () => {
    const user = await openPreview()
    await user.click(screen.getByRole('checkbox', { name: '選取 !hug' }))
    await user.click(screen.getByRole('switch', { name: '匯入後啟用 !discord' }))
    await user.click(screen.getByRole('button', { name: /匯入勾選的/ }))

    await waitFor(() => expect(api.applyImport).toHaveBeenCalled())
    expect(api.applyImport).toHaveBeenCalledWith('imp-1', {
      'builtin:followage': false,
      'cmd:discord': true,
    })
  })

  it('refreshes the page data and closes once applied', async () => {
    const user = userEvent.setup()
    const onImported = vi.fn()
    const onClose = vi.fn()
    render(<ImportSheet open onImported={onImported} onClose={onClose} />)
    await user.click(await screen.findByText('StreamElements'))
    await screen.findByText('新增為自訂指令')
    await user.click(screen.getByRole('button', { name: /匯入勾選的/ }))

    await waitFor(() => expect(onImported).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
  })
})

describe('ImportSheet returning from OAuth', () => {
  it('loads the stashed preview when handed an import id', async () => {
    renderSheet({ initialImportId: 'imp-1' })
    await waitFor(() => expect(api.getImportPreview).toHaveBeenCalledWith('imp-1'))
    const custom = await screen.findByText('新增為自訂指令')
    expect(custom).toBeInTheDocument()
    expect(within(document.body).getByText(/niistream/)).toBeInTheDocument()
  })
})
