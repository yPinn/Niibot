import { API_ENDPOINTS, apiFetch } from './config'
import { ApiError, apiJson, NETWORK_ERROR, parseApiError } from './errors'

export interface CheckinSettings {
  channel_id: string
  timezone: string
  success_template: string
  duplicate_template: string
  reply_delay_seconds: number
  created_at: string | null
  updated_at: string | null
}

export interface CheckinSettingsUpdate {
  timezone: string
  success_template: string
  duplicate_template: string
  reply_delay_seconds: number
}

export interface CheckinLeaderboardEntry {
  rank: number
  user_id: string
  username: string
  display_name: string | null
  total_days: number
  last_checkin_date: string
}

export type CheckinImportRowStatus = 'ready' | 'review' | 'invalid' | 'unresolved' | 'conflict'

export interface CheckinImportRow {
  key: string
  source_row: number
  user_id: string | null
  username: string | null
  display_name: string | null
  total_days: number | null
  last_checkin_date: string | null
  current_streak: number | null
  daily_order: number | null
  status: CheckinImportRowStatus
  issues: string[]
}

export interface CheckinImportPreview {
  import_id: string
  source: string
  source_format: 'csv' | 'tsv' | 'xlsx' | 'google_sheets'
  source_timezone: string
  through_date: string
  sheet_name: string | null
  rows: CheckinImportRow[]
  default_selection: Record<string, boolean>
}

export type CheckinImportCanonicalField =
  | 'platform_user_id'
  | 'username'
  | 'display_name'
  | 'total_days'
  | 'last_checkin_date'
  | 'current_streak'
  | 'daily_order'

export type CheckinImportColumnMapping = Partial<Record<CheckinImportCanonicalField, number>>

export interface CheckinImportColumns {
  source_format: 'csv' | 'tsv' | 'xlsx' | 'google_sheets'
  sheet_name: string | null
  headers: string[]
  suggested_mapping: CheckinImportColumnMapping
}

export interface CheckinImportSourceInput {
  upload?: File
  sheetUrl?: string
  sheetName?: string
}

export interface CheckinImportPreviewInput extends CheckinImportSourceInput {
  source: string
  sourceTimezone: string
  throughDate: string
  columnMapping?: CheckinImportColumnMapping
}

export interface CheckinImportApplyResult {
  batch_id: string
  imported_rows: number
  already_applied: boolean
}

export type CheckinClearScope = 'imported' | 'all'

export interface CheckinDataCounts {
  participant_count: number
  total_days: number
  imported_viewers: number
  imported_days: number
  ledger_checkins: number
  card_draws: number
  checkin_events: number
}

export interface CheckinDataSummary extends CheckinDataCounts {
  confirmation_text: string
}

export interface CheckinDataClearResult extends CheckinDataCounts {
  scope: CheckinClearScope
}

export interface CheckinDataDownload {
  blob: Blob
  filename: string
}

export function getCheckinSettings(): Promise<CheckinSettings> {
  return apiJson(
    API_ENDPOINTS.checkin.settings,
    { credentials: 'include' },
    { fallback: '載入簽到設定失敗' }
  )
}

export function getCheckinLeaderboard(): Promise<CheckinLeaderboardEntry[]> {
  return apiJson(
    API_ENDPOINTS.checkin.leaderboard,
    { credentials: 'include' },
    { fallback: '載入簽到排行榜失敗' }
  )
}

export function updateCheckinSettings(update: CheckinSettingsUpdate): Promise<CheckinSettings> {
  return apiJson(
    API_ENDPOINTS.checkin.settings,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-settings',
      },
      body: JSON.stringify(update),
    },
    { fallback: '儲存簽到設定失敗' }
  )
}

export function getCheckinDataSummary(): Promise<CheckinDataSummary> {
  return apiJson(
    API_ENDPOINTS.checkin.dataSummary,
    { credentials: 'include' },
    { fallback: '載入簽到資料摘要失敗' }
  )
}

function downloadFilename(response: Response): string {
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded.replace(/^"|"$/g, ''))
    } catch {
      // Fall through to the ASCII filename when the extended value is invalid.
    }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? 'niibot-checkins.csv'
}

export async function exportCheckinData(): Promise<CheckinDataDownload> {
  let response: Response
  try {
    response = await apiFetch(API_ENDPOINTS.checkin.dataExport, { credentials: 'include' })
  } catch {
    throw new ApiError({
      message: '網路連線出了問題，請檢查後再試',
      status: 0,
      code: NETWORK_ERROR,
    })
  }
  if (!response.ok) throw await parseApiError(response, '匯出簽到資料失敗')
  return { blob: await response.blob(), filename: downloadFilename(response) }
}

export function clearCheckinData(
  scope: CheckinClearScope,
  confirmation: string
): Promise<CheckinDataClearResult> {
  return apiJson(
    API_ENDPOINTS.checkin.dataClear,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-data',
      },
      body: JSON.stringify({ scope, confirmation }),
    },
    { fallback: '清除簽到資料失敗' }
  )
}

export function previewCheckinImport(
  input: CheckinImportPreviewInput
): Promise<CheckinImportPreview> {
  const body = new FormData()
  body.set('source', input.source)
  body.set('source_timezone', input.sourceTimezone)
  body.set('through_date', input.throughDate)
  if (input.upload) body.set('upload', input.upload)
  if (input.sheetUrl) body.set('sheet_url', input.sheetUrl)
  if (input.sheetName) body.set('sheet_name', input.sheetName)
  if (input.columnMapping) body.set('column_mapping', JSON.stringify(input.columnMapping))
  return apiJson(
    API_ENDPOINTS.checkin.importPreview,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'checkin-import' },
      body,
    },
    { fallback: '讀取簽到資料失敗' }
  )
}

export function inspectCheckinImportColumns(
  input: CheckinImportSourceInput
): Promise<CheckinImportColumns> {
  const body = new FormData()
  if (input.upload) body.set('upload', input.upload)
  if (input.sheetUrl) body.set('sheet_url', input.sheetUrl)
  if (input.sheetName) body.set('sheet_name', input.sheetName)
  return apiJson(
    API_ENDPOINTS.checkin.importColumns,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'checkin-import' },
      body,
    },
    { fallback: '讀取來源欄位失敗' }
  )
}

export function applyCheckinImport(
  importId: string,
  selectedKeys: string[],
  oldSourceDisabled: boolean
): Promise<CheckinImportApplyResult> {
  return apiJson(
    API_ENDPOINTS.checkin.importApply,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-import',
      },
      body: JSON.stringify({
        import_id: importId,
        selected_keys: selectedKeys,
        old_source_disabled: oldSourceDisabled,
      }),
    },
    { fallback: '套用簽到資料失敗' }
  )
}
