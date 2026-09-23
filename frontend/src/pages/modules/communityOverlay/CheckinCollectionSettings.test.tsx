import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/checkin', () => ({
  getCheckinCollections: vi.fn(),
  updateCheckinCollection: vi.fn(),
}))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

import { toast } from 'sonner'

import {
  type CheckinCollectionCatalog,
  getCheckinCollections,
  updateCheckinCollection,
} from '@/api/checkin'
import { toastApiError } from '@/lib/toast-error'

import { CheckinCollectionSettings } from './CheckinCollectionSettings'

const CATALOG: CheckinCollectionCatalog = {
  selected_set_key: null,
  total_cards: 3,
  sets: [
    {
      key: 'aespa',
      name: 'aespa',
      card_count: 2,
      cards: [
        {
          key: 'karina-01',
          number: 1,
          name: 'Karina',
          portrait_url: '/images/collections/aespa/karina-01-r1.webp',
          rarity_key: 'common',
          rarity_name: '普通',
        },
        {
          key: 'winter-01',
          number: 2,
          name: 'Winter',
          portrait_url: '/images/collections/aespa/winter-01-r1.webp',
          rarity_key: 'common',
          rarity_name: '普通',
        },
      ],
    },
    {
      key: 'uc',
      name: 'Eunha',
      card_count: 1,
      cards: [
        {
          key: 'eunha-01',
          number: 1,
          name: 'Eunha',
          portrait_url: '/images/collections/uc/eunha-01-r1.webp',
          rarity_key: 'common',
          rarity_name: '普通',
        },
      ],
    },
  ],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

describe('CheckinCollectionSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCheckinCollections).mockResolvedValue(CATALOG)
    vi.mocked(updateCheckinCollection).mockImplementation(async setKey => ({
      ...CATALOG,
      selected_set_key: setKey,
    }))
  })

  it('keeps a stable loading state while the catalog request is pending', () => {
    const pending = deferred<CheckinCollectionCatalog>()
    vi.mocked(getCheckinCollections).mockReturnValueOnce(pending.promise)

    render(<CheckinCollectionSettings />)

    expect(screen.getByLabelText('載入卡片設定')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '抽卡範圍' })).not.toBeInTheDocument()
  })

  it('shows an explicit empty state when no cards are published', async () => {
    vi.mocked(getCheckinCollections).mockResolvedValueOnce({
      selected_set_key: null,
      total_cards: 0,
      sets: [],
    })

    render(<CheckinCollectionSettings />)

    expect(await screen.findByText('目前沒有可用卡片')).toBeInTheDocument()
  })

  it('loads all sets as the default draw range and opens the catalog', async () => {
    const user = userEvent.setup()
    render(<CheckinCollectionSettings />)

    expect(await screen.findByRole('combobox', { name: '抽卡範圍' })).toHaveTextContent('全部卡組')
    expect(screen.getByText('3 張 · 2 個卡組')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '查看卡片圖鑑' }))
    const dialog = screen.getByRole('dialog', { name: '卡片圖鑑' })
    expect(within(dialog).getAllByRole('img')).toHaveLength(3)
    expect(within(dialog).getByRole('img', { name: 'aespa #001 Karina' })).toHaveAttribute(
      'loading',
      'lazy'
    )
    expect(within(dialog).getByRole('button', { name: 'aespa 2' })).toBeInTheDocument()
  })

  it('filters the catalog without changing the active draw range', async () => {
    const user = userEvent.setup()
    render(<CheckinCollectionSettings />)

    await user.click(await screen.findByRole('button', { name: '查看卡片圖鑑' }))
    const dialog = screen.getByRole('dialog', { name: '卡片圖鑑' })
    await user.click(within(dialog).getByRole('button', { name: 'Eunha 1' }))

    expect(within(dialog).getAllByRole('img')).toHaveLength(1)
    expect(within(dialog).getByRole('img', { name: 'Eunha #001 Eunha' })).toBeInTheDocument()
    expect(updateCheckinCollection).not.toHaveBeenCalled()
  })

  it('saves one set immediately and keeps the returned server selection', async () => {
    const user = userEvent.setup()
    render(<CheckinCollectionSettings />)

    await user.click(await screen.findByRole('combobox', { name: '抽卡範圍' }))
    await user.click(screen.getByRole('option', { name: 'aespa（2 張）' }))

    await waitFor(() => expect(updateCheckinCollection).toHaveBeenCalledWith('aespa'))
    expect(screen.getByRole('combobox', { name: '抽卡範圍' })).toHaveTextContent('aespa')
    expect(toast.success).toHaveBeenCalledWith('抽卡範圍已更新')
  })

  it('returns a selected set to the all-sets fallback', async () => {
    const user = userEvent.setup()
    vi.mocked(getCheckinCollections).mockResolvedValueOnce({
      ...CATALOG,
      selected_set_key: 'aespa',
    })
    render(<CheckinCollectionSettings />)

    await user.click(await screen.findByRole('combobox', { name: '抽卡範圍' }))
    await user.click(screen.getByRole('option', { name: '全部卡組（3 張）' }))

    await waitFor(() => expect(updateCheckinCollection).toHaveBeenCalledWith(null))
  })

  it('uses the bundled image sample without tenant API calls in preview mode', async () => {
    render(<CheckinCollectionSettings preview />)

    expect(screen.getByRole('combobox', { name: '抽卡範圍' })).toHaveTextContent('全部卡組')
    expect(getCheckinCollections).not.toHaveBeenCalled()
  })

  it('restores the previous selection when saving fails', async () => {
    const user = userEvent.setup()
    const error = new Error('offline')
    vi.mocked(updateCheckinCollection).mockRejectedValueOnce(error)
    render(<CheckinCollectionSettings />)

    await user.click(await screen.findByRole('combobox', { name: '抽卡範圍' }))
    await user.click(screen.getByRole('option', { name: 'aespa（2 張）' }))

    await waitFor(() => expect(toastApiError).toHaveBeenCalledWith(error, '更新抽卡範圍失敗'))
    expect(screen.getByRole('combobox', { name: '抽卡範圍' })).toHaveTextContent('全部卡組')
  })

  it('shows a recoverable load error', async () => {
    const user = userEvent.setup()
    vi.mocked(getCheckinCollections)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(CATALOG)
    render(<CheckinCollectionSettings />)

    expect(await screen.findByText('卡片圖鑑載入失敗')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新載入卡片圖鑑' }))

    expect(await screen.findByRole('combobox', { name: '抽卡範圍' })).toHaveTextContent('全部卡組')
  })
})
