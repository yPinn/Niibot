import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

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

export interface CheckinImportPreviewInput {
  source: string
  sourceTimezone: string
  throughDate: string
  upload?: File
  sheetUrl?: string
  sheetName?: string
}

export interface CheckinImportApplyResult {
  batch_id: string
  imported_rows: number
  already_applied: boolean
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
