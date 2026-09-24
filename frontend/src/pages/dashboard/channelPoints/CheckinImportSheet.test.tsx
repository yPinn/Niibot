import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/checkin', () => ({
  inspectCheckinImportColumns: vi.fn(),
  previewCheckinImport: vi.fn(),
  applyCheckinImport: vi.fn(),
  remapCheckinImportIdentities: vi.fn(),
}))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

import {
  applyCheckinImport,
  inspectCheckinImportColumns,
  previewCheckinImport,
  remapCheckinImportIdentities,
} from '@/api/checkin'

import { CheckinImportSheet } from './CheckinImportSheet'

const PREVIEW = {
  import_id: 'preview-1',
  source: 'chiwabots',
  source_format: 'csv' as const,
  source_timezone: 'Asia/Taipei',
  through_date: '2026-09-10',
  sheet_name: null,
  rows: [
    {
      key: 'row-ready',
      source_row: 2,
      user_id: '101',
      username: 'alice',
      display_name: 'Alice',
      total_days: 15,
      last_checkin_date: '2026-09-10',
      current_streak: 3,
      daily_order: 5,
      status: 'ready' as const,
      issues: [],
      source_user_id: null,
      source_username: 'alice',
      source_display_name: null,
      identity_resolution: 'username' as const,
    },
    {
      key: 'row-conflict',
      source_row: 3,
      user_id: '102',
      username: 'bob',
      display_name: 'Bob',
      total_days: 8,
      last_checkin_date: '2026-09-09',
      current_streak: 1,
      daily_order: null,
      status: 'conflict' as const,
      issues: ['這位觀眾已有資料'],
      source_user_id: null,
      source_username: 'bob',
      source_display_name: null,
      identity_resolution: 'username' as const,
    },
  ],
  default_selection: { 'row-ready': true, 'row-conflict': false },
}

const AUTO_COLUMNS = {
  source_format: 'csv' as const,
  sheet_name: null,
  headers: ['Username', 'Count', 'LastDate', 'Streak', 'TodayOrder'],
  suggested_mapping: {
    username: 0,
    total_days: 1,
    last_checkin_date: 2,
    current_streak: 3,
    daily_order: 4,
  },
}

const MANUAL_COLUMNS = {
  source_format: 'csv' as const,
  sheet_name: null,
  headers: ['觀眾帳戶', '累計簽到', '最近一次', '連續紀錄'],
  suggested_mapping: {},
}

describe('CheckinImportSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(inspectCheckinImportColumns).mockResolvedValue(AUTO_COLUMNS)
    vi.mocked(previewCheckinImport).mockResolvedValue(PREVIEW)
    vi.mocked(applyCheckinImport).mockResolvedValue({
      batch_id: 'batch-1',
      imported_rows: 1,
      already_applied: false,
    })
    vi.mocked(remapCheckinImportIdentities).mockResolvedValue(PREVIEW)
  })

  it('previews recognized files without writing, then requires explicit cutover confirmation', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<CheckinImportSheet open onOpenChange={onOpenChange} defaultTimezone="Asia/Taipei" />)

    expect(screen.queryByRole('button', { name: /確認匯入/ })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('簽到資料來源'), 'nightbot')
    await user.click(screen.getByRole('combobox', { name: '來源時區' }))
    await user.click(screen.getByRole('option', { name: 'UTC（UTC+0）' }))
    await user.clear(screen.getByLabelText('資料截止日'))
    await user.type(screen.getByLabelText('資料截止日'), '2026-09-10')
    const input = screen.getByLabelText('選擇簽到資料檔案')
    expect(input).toHaveAttribute('accept', expect.stringContaining('.xlsx'))
    await user.upload(
      input,
      new File(['Username,Count,LastDate\nalice,15,2026-09-10'], 'checkins.csv', {
        type: 'text/csv',
      })
    )
    await user.click(screen.getByRole('button', { name: '讀取並預覽' }))

    expect(await screen.findByText('Alice')).toBeInTheDocument()
    expect(previewCheckinImport).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'nightbot',
        sourceTimezone: 'UTC',
        throughDate: '2026-09-10',
        columnMapping: {
          username: 0,
          total_days: 1,
          last_checkin_date: 2,
          current_streak: 3,
          daily_order: 4,
        },
      })
    )
    expect(applyCheckinImport).not.toHaveBeenCalled()
    expect(screen.getByText(/尚未寫入任何資料/)).toBeInTheDocument()
    expect(screen.getByText('資料衝突')).toBeInTheDocument()
    expect(screen.queryByText('101')).not.toBeInTheDocument()
    expect(screen.getByLabelText('選取 Bob')).toBeDisabled()
    expect(screen.getByRole('button', { name: '確認匯入 1 筆' })).toBeDisabled()

    await user.click(screen.getByLabelText('選取 Alice'))
    expect(screen.getByRole('button', { name: '確認匯入 0 筆' })).toBeDisabled()
    await user.click(screen.getByLabelText('選取 Alice'))
    await user.click(screen.getByLabelText('我已停用舊 Bot 的簽到'))
    await user.click(screen.getByRole('button', { name: '確認匯入 1 筆' }))

    expect(applyCheckinImport).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog', { name: '確認匯入簽到資料' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '確定匯入' }))

    expect(applyCheckinImport).toHaveBeenCalledWith('preview-1', ['row-ready'], true)
    expect(await screen.findByText(/已匯入 1 位觀眾/)).toBeInTheDocument()
    expect(screen.queryByText('batch-1')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看技術資訊' }))
    expect(screen.getByText(/batch-1/)).toBeInTheDocument()
    expect(onOpenChange).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '關閉' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('asks for manual mapping only when required columns cannot be recognized', async () => {
    vi.mocked(inspectCheckinImportColumns).mockResolvedValue(MANUAL_COLUMNS)
    const user = userEvent.setup()
    render(<CheckinImportSheet open onOpenChange={vi.fn()} defaultTimezone="Asia/Taipei" />)

    await user.upload(
      screen.getByLabelText('選擇簽到資料檔案'),
      new File(['觀眾帳戶,累計簽到,最近一次'], 'checkins.csv', { type: 'text/csv' })
    )
    await user.click(screen.getByRole('button', { name: '讀取並預覽' }))

    expect(await screen.findByText('還需要對應必要欄位')).toBeInTheDocument()
    expect(previewCheckinImport).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /確認匯入/ })).not.toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Twitch 帳號 對應欄位' }), '0')
    await user.selectOptions(screen.getByLabelText('累積天數 對應欄位'), '1')
    await user.selectOptions(screen.getByLabelText('最後簽到 對應欄位'), '2')
    await user.click(screen.getByText('其他欄位（可選）'))
    await user.selectOptions(screen.getByLabelText('連續天數 對應欄位'), '3')
    await user.click(screen.getByRole('button', { name: '更新預覽' }))

    expect(await screen.findByText('Alice')).toBeInTheDocument()
    expect(previewCheckinImport).toHaveBeenCalledWith(
      expect.objectContaining({
        columnMapping: {
          username: 0,
          total_days: 1,
          last_checkin_date: 2,
          current_streak: 3,
        },
      })
    )
  })

  it('explains and accepts public Google Sheets links without OAuth credentials', async () => {
    const user = userEvent.setup()
    render(<CheckinImportSheet open onOpenChange={vi.fn()} defaultTimezone="Asia/Taipei" />)

    await user.click(screen.getByRole('button', { name: 'Google Sheets' }))
    expect(screen.getByText(/私人表格 OAuth 尚未支援/)).toBeInTheDocument()
    await user.type(
      screen.getByLabelText('Google Sheets 連結'),
      'https://docs.google.com/spreadsheets/d/abc123/edit?gid=0'
    )
    await user.click(screen.getByRole('button', { name: '讀取並預覽' }))

    expect(await screen.findByText('Alice')).toBeInTheDocument()

    expect(inspectCheckinImportColumns).toHaveBeenCalledWith(
      expect.objectContaining({
        sheetUrl: 'https://docs.google.com/spreadsheets/d/abc123/edit?gid=0',
        upload: undefined,
      })
    )
  })

  it('maps an unresolved old username to a verified current account for review', async () => {
    const unresolved = {
      ...PREVIEW,
      import_id: 'preview-old',
      rows: [
        PREVIEW.rows[0],
        {
          key: 'row-old',
          source_row: 3,
          user_id: null,
          username: null,
          display_name: null,
          total_days: 8,
          last_checkin_date: '2026-09-09',
          current_streak: 1,
          daily_order: 4,
          status: 'unresolved' as const,
          issues: ['找不到可確認的 Twitch 帳號'],
          source_user_id: null,
          source_username: 'alice_old',
          source_display_name: null,
          identity_resolution: null,
        },
      ],
      default_selection: { 'row-ready': true, 'row-old': false },
    }
    const remapped = {
      ...unresolved,
      import_id: 'preview-new',
      rows: [
        unresolved.rows[0],
        {
          ...unresolved.rows[1],
          user_id: '202',
          username: 'alice_new',
          display_name: 'Alice New',
          status: 'review' as const,
          issues: ['已配對目前帳號，請確認'],
          identity_resolution: 'manual' as const,
        },
      ],
    }
    vi.mocked(previewCheckinImport).mockResolvedValue(unresolved)
    vi.mocked(remapCheckinImportIdentities).mockResolvedValue(remapped)
    const user = userEvent.setup()
    render(<CheckinImportSheet open onOpenChange={vi.fn()} defaultTimezone="Asia/Taipei" />)

    await user.upload(
      screen.getByLabelText('選擇簽到資料檔案'),
      new File(['Username,Count,LastDate'], 'checkins.csv', { type: 'text/csv' })
    )
    await user.click(screen.getByRole('button', { name: '讀取並預覽' }))

    expect(await screen.findByText('@alice_old')).toBeInTheDocument()
    expect(screen.getByText('待配對')).toBeInTheDocument()
    const readyName = screen.getByText('Alice')
    const oldName = screen.getByText('@alice_old')
    expect(
      oldName.compareDocumentPosition(readyName) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '指定 alice_old 的現行帳號' }))
    await user.type(screen.getByLabelText('目前 Twitch 帳號'), 'alice_new')
    await user.click(screen.getByRole('button', { name: '驗證配對' }))

    expect(remapCheckinImportIdentities).toHaveBeenCalledWith('preview-old', [
      { rowKey: 'row-old', targetType: 'username', value: 'alice_new' },
    ])
    expect(await screen.findByText('Alice New')).toBeInTheDocument()
    expect(screen.getByText('@alice_new')).toBeInTheDocument()
    expect(screen.getByText(/來源 @alice_old/)).toBeInTheDocument()
    expect(screen.getByText('待確認')).toBeInTheDocument()
    expect(screen.getByLabelText('選取 Alice New')).not.toBeDisabled()
    expect(screen.getByLabelText('選取 Alice New')).not.toBeChecked()
    expect(screen.queryByText('202')).not.toBeInTheDocument()
  })

  it('keeps the mapping form open when Twitch cannot find the replacement account', async () => {
    const unresolved = {
      ...PREVIEW,
      import_id: 'preview-old',
      rows: [
        {
          ...PREVIEW.rows[0],
          key: 'row-old',
          user_id: null,
          username: null,
          display_name: null,
          status: 'unresolved' as const,
          issues: ['找不到 Twitch 帳號，可指定目前帳號'],
          source_username: 'alice_old',
          identity_resolution: null,
        },
      ],
      default_selection: { 'row-old': false },
    }
    const notFound = {
      ...unresolved,
      import_id: 'preview-retry',
      rows: [
        {
          ...unresolved.rows[0],
          issues: ['找不到指定的 Twitch 帳號，請重新輸入'],
        },
      ],
    }
    vi.mocked(previewCheckinImport).mockResolvedValue(unresolved)
    vi.mocked(remapCheckinImportIdentities).mockResolvedValue(notFound)
    const user = userEvent.setup()
    render(<CheckinImportSheet open onOpenChange={vi.fn()} defaultTimezone="Asia/Taipei" />)

    await user.upload(
      screen.getByLabelText('選擇簽到資料檔案'),
      new File(['Username,Count,LastDate'], 'checkins.csv', { type: 'text/csv' })
    )
    await user.click(screen.getByRole('button', { name: '讀取並預覽' }))
    await user.click(screen.getByRole('button', { name: '指定 alice_old 的現行帳號' }))
    await user.type(screen.getByLabelText('目前 Twitch 帳號'), 'missing_user')
    await user.click(screen.getByRole('button', { name: '驗證配對' }))

    expect(await screen.findByText('找不到指定的 Twitch 帳號，請重新輸入')).toBeInTheDocument()
    expect(screen.getByLabelText('目前 Twitch 帳號')).toHaveValue('missing_user')
  })
})
