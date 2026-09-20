import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/checkin', () => ({
  inspectCheckinImportColumns: vi.fn(),
  previewCheckinImport: vi.fn(),
  applyCheckinImport: vi.fn(),
}))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

import {
  applyCheckinImport,
  inspectCheckinImportColumns,
  previewCheckinImport,
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
  })

  it('previews recognized files without writing, then requires explicit cutover confirmation', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<CheckinImportSheet open onOpenChange={onOpenChange} defaultTimezone="Asia/Taipei" />)

    expect(screen.queryByRole('button', { name: /確認匯入/ })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('簽到資料來源'), 'nightbot')
    await user.clear(screen.getByLabelText('來源時區'))
    await user.type(screen.getByLabelText('來源時區'), 'UTC')
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
    expect(screen.getByText('已有資料')).toBeInTheDocument()
    expect(screen.getByLabelText('選取 Bob')).toBeDisabled()
    expect(screen.getByRole('button', { name: '確認匯入 1 筆' })).toBeDisabled()

    await user.click(screen.getByLabelText('選取 Alice'))
    expect(screen.getByRole('button', { name: '確認匯入 0 筆' })).toBeDisabled()
    await user.click(screen.getByLabelText('選取 Alice'))
    await user.click(screen.getByLabelText('我已停用舊 Bot 的簽到'))
    await user.click(screen.getByRole('button', { name: '確認匯入 1 筆' }))

    expect(applyCheckinImport).toHaveBeenCalledWith('preview-1', ['row-ready'], true)
    expect(await screen.findByText(/批次編號：batch-1/)).toBeInTheDocument()
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

    await user.selectOptions(screen.getByLabelText('Username 對應欄位'), '0')
    await user.selectOptions(screen.getByLabelText('Count 對應欄位'), '1')
    await user.selectOptions(screen.getByLabelText('LastDate 對應欄位'), '2')
    await user.click(screen.getByText('其他欄位（可選）'))
    await user.selectOptions(screen.getByLabelText('Streak 對應欄位'), '3')
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
})
