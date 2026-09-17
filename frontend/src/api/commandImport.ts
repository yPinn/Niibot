import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export type ImportSourceName = 'nightbot' | 'streamelements'

/** Which part of the preview a row belongs to. */
export type ImportSection = 'builtin' | 'custom' | 'trigger' | 'unsupported'

/** How faithfully the row will survive the move. */
export type ImportStatus = 'ok' | 'review' | 'conflict' | 'unsupported'

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
