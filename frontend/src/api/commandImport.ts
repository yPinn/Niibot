import { API_ENDPOINTS, apiFetch } from './config'
import { ApiError, apiJson, NETWORK_ERROR, parseApiError } from './errors'

export type ImportSourceName = 'nightbot' | 'streamelements' | 'csv'

/** Which part of the preview a row belongs to. */
export type ImportSection = 'builtin' | 'custom' | 'trigger' | 'unsupported'

/** How faithfully the row will survive the move. */
export type ImportStatus = 'ok' | 'review' | 'conflict' | 'unsupported'

export type ImportFieldAction = 'preserved' | 'tightened' | 'dropped' | 'review'

export interface ImportFieldOutcome {
  field: string
  action: ImportFieldAction
  detail: string
}

export interface ImportSourceInfo {
  source: ImportSourceName
  available: boolean
  reason: string | null
}

export interface ImportItem {
  key: string
  section: ImportSection
  status: ImportStatus
  source_name: string
  /** Whether the command was switched on over at the old bot. */
  source_enabled: boolean
  notes: string[]
  /** Explicit per-field conversion result for defaults and approximate mappings. */
  field_outcomes: ImportFieldOutcome[]
  command_name: string | null
  response: string | null
  original_response: string | null
  cooldown: number | null
  min_role: string
  aliases: string[]
  pattern: string | null
  match_type: string
  builtin_target: string | null
}

export interface ImportPreview {
  import_id: string
  source: ImportSourceName
  source_channel: string
  items: ImportItem[]
  /** Item key → start enabled. Omitted keys are unticked. */
  default_selection: Record<string, boolean>
}

export interface ImportResult {
  created: number
  enabled: number
  skipped: number
  failed: number
  errors: string[]
}

export interface CommandCsvDownload {
  blob: Blob
  filename: string
}

export function getImportSources(): Promise<ImportSourceInfo[]> {
  return apiJson(
    API_ENDPOINTS.commandImport.sources,
    { credentials: 'include' },
    { fallback: '載入匯入來源失敗' }
  )
}

export function previewStreamElements(): Promise<ImportPreview> {
  return apiJson(
    API_ENDPOINTS.commandImport.streamelementsPreview,
    { credentials: 'include' },
    { fallback: '讀取 StreamElements 指令失敗' }
  )
}

export function previewCommandCsv(upload: File): Promise<ImportPreview> {
  const body = new FormData()
  body.set('upload', upload)
  return apiJson(
    API_ENDPOINTS.commandImport.csvPreview,
    { method: 'POST', credentials: 'include', body },
    { fallback: '讀取 CSV 指令失敗' }
  )
}

export async function exportCommandCsv(): Promise<CommandCsvDownload> {
  let response: Response
  try {
    response = await apiFetch(API_ENDPOINTS.commandImport.csvExport, { credentials: 'include' })
  } catch {
    throw new ApiError({
      message: '網路連線出了問題，請檢查後再試',
      status: 0,
      code: NETWORK_ERROR,
    })
  }
  if (!response.ok) throw await parseApiError(response, '匯出指令失敗')
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? 'niibot-commands.csv'
  return { blob: await response.blob(), filename }
}

export function getNightbotOauthUrl(): Promise<{ oauth_url: string }> {
  return apiJson(
    API_ENDPOINTS.commandImport.nightbotOauth,
    { credentials: 'include' },
    { fallback: '無法開始 Nightbot 授權' }
  )
}

export function getImportPreview(importId: string): Promise<ImportPreview> {
  return apiJson(
    API_ENDPOINTS.commandImport.preview(importId),
    { credentials: 'include' },
    { fallback: '讀取匯入清單失敗' }
  )
}

export function applyImport(
  importId: string,
  selections: Record<string, boolean>
): Promise<ImportResult> {
  return apiJson(
    API_ENDPOINTS.commandImport.apply,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ import_id: importId, selections }),
    },
    { fallback: '匯入失敗' }
  )
}
