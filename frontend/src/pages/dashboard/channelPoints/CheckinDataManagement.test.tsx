import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/checkin', () => ({
  clearCheckinData: vi.fn(),
  exportCheckinData: vi.fn(),
  getCheckinDataSummary: vi.fn(),
}))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

import { clearCheckinData, exportCheckinData, getCheckinDataSummary } from '@/api/checkin'

import { CheckinDataManagement } from './CheckinDataManagement'

const SUMMARY = {
  participant_count: 2,
  total_days: 19,
  imported_viewers: 1,
  imported_days: 15,
  ledger_checkins: 4,
  card_draws: 4,
  checkin_events: 4,
  confirmation_text: 'owner_login',
}

describe('CheckinDataManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCheckinDataSummary).mockResolvedValue(SUMMARY)
    vi.mocked(clearCheckinData).mockResolvedValue({ ...SUMMARY, scope: 'imported' })
    vi.mocked(exportCheckinData).mockResolvedValue({
      blob: new Blob(['csv']),
      filename: 'owner-checkins.csv',
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:checkin-export'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('keeps one clear entry and defaults to the reversible imported-data scope', async () => {
    const user = userEvent.setup()
    render(<CheckinDataManagement onDataChanged={vi.fn()} />)

    expect(screen.getByRole('button', { name: '匯出 CSV' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '清除簽到資料' })).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: '清除簽到資料' }))

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /只撤銷轉移資料/ })).toBeChecked()
    expect(screen.getByText(/1 位觀眾、15 天轉移資料/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /清除全部簽到與收藏/ })).not.toBeChecked()
  })

  it('requires the channel name before clearing and refreshes visible data', async () => {
    const user = userEvent.setup()
    const onDataChanged = vi.fn().mockResolvedValue(undefined)
    render(<CheckinDataManagement onDataChanged={onDataChanged} />)

    await user.click(screen.getByRole('button', { name: '清除簽到資料' }))
    const confirmation = await screen.findByRole('textbox', { name: '輸入頻道名稱以確認' })
    const clearButton = screen.getByRole('button', { name: '確認清除' })
    expect(clearButton).toBeDisabled()

    await user.type(confirmation, 'owner_login')
    expect(clearButton).toBeEnabled()
    await user.click(clearButton)

    await waitFor(() => expect(clearCheckinData).toHaveBeenCalledWith('imported', 'owner_login'))
    expect(onDataChanged).toHaveBeenCalledOnce()
  })

  it('reveals the card loss only after explicitly choosing full clear', async () => {
    const user = userEvent.setup()
    render(<CheckinDataManagement onDataChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: '清除簽到資料' }))
    await user.click(await screen.findByRole('radio', { name: /清除全部簽到與收藏/ }))

    expect(screen.getByText(/4 筆簽到與 4 張收藏卡/)).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: '輸入頻道名稱以確認' }), 'owner_login')
    await user.click(screen.getByRole('button', { name: '確認清除' }))

    await waitFor(() => expect(clearCheckinData).toHaveBeenCalledWith('all', 'owner_login'))
  })

  it('downloads the portable export without opening another workflow', async () => {
    const user = userEvent.setup()
    render(<CheckinDataManagement onDataChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: '匯出 CSV' }))

    await waitFor(() => expect(exportCheckinData).toHaveBeenCalledOnce())
    expect(URL.createObjectURL).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledOnce()
  })
})
