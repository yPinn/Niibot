import { API_ENDPOINTS, apiFetch } from './config'
import { ApiError, apiJson, NETWORK_ERROR, parseApiError } from './errors'

export type SourceKind = 'original' | 'existing_work'
export type CanonMode = 'original' | 'canon' | 'alternate_universe'
export type SpoilerPolicy = 'forbid' | 'allow_within_scope'
export type ChannelStage = 'in_world_visitors' | 'chat_adapted' | 'cross_world'
export type RelationshipState =
  'unfamiliar' | 'guarded' | 'familiar' | 'trusted' | 'hostile' | 'intimate'

export interface RoleplayRelationship {
  subject: string
  role: string
  state: RelationshipState
  notes: string
}

export interface RoleplayLoreEntry {
  subject: string
  aliases: string[]
  content: string
  known_at_stage: boolean
  contains_spoilers: boolean
  priority: number
}

export interface RoleplayPackage {
  schema_version: 1
  name: string
  world: {
    title: string
    source_kind: SourceKind
    canon_mode: CanonMode
    canon_scope: string
    world_anchor: string
    story_stage: string
    spoiler_policy: SpoilerPolicy
  }
  character: {
    name: string
    role: string
    motivation: string
    stable_traits: string[]
    boundaries: string[]
    voice: string
    relationships: RoleplayRelationship[]
    knowledge: { known: string[]; unknown: string[] }
  }
  scene: {
    location: string
    current_activity: string
    current_goal: string
    emotional_baseline: string
    channel_stage: ChannelStage
    host_relationship: string
    audience_relationship: string
    adaptation_note: string
    host_character_mapping: string | null
    audience_character_mapping: null
  }
  lore_entries: RoleplayLoreEntry[]
  example_replies: string[]
}

export interface RoleplayRevisionSummary {
  id: number
  revision_number: number
  schema_version: number
  compiler_version: number
  content_digest: string
  published_at: string
}

export interface RoleplayRevision extends RoleplayRevisionSummary {
  roleplay_set_id: string
  package: RoleplayPackage
  capsule: string
  compact_capsule: string
}

export interface RoleplaySetSummary {
  id: string
  name: string
  draft_version: number
  published: RoleplayRevisionSummary | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface RoleplaySet extends RoleplaySetSummary {
  draft: RoleplayPackage
}

export interface AssistantMode {
  assistant_mode: 'persona' | 'roleplay'
  active_roleplay_revision_id: number | null
}

export type RoleplayImportMode = 'use' | 'copy'

export interface RoleplayCharacterFile {
  format: 'niibot.roleplay-character'
  format_version: 1
  manifest: {
    name: string
    exported_at: string
    schema_version: number
    compiler_version: number
    content_digest: string
  }
  package: RoleplayPackage
  compiled_preview: {
    capsule: string
    compact_capsule: string
  }
}

export interface RoleplayImportResult {
  mode: RoleplayImportMode
  reused: boolean
  roleplay_set: RoleplaySet
  active_roleplay_revision_id: number | null
}

export interface RoleplayExportDownload {
  blob: Blob
  filename: string
}

export const MAX_ROLEPLAY_FILE_BYTES = 128 * 1024

export function createEmptyRoleplayPackage(): RoleplayPackage {
  return {
    schema_version: 1,
    name: '',
    world: {
      title: '',
      source_kind: 'original',
      canon_mode: 'original',
      canon_scope: '',
      world_anchor: '',
      story_stage: '',
      spoiler_policy: 'forbid',
    },
    character: {
      name: '',
      role: '',
      motivation: '',
      stable_traits: [],
      boundaries: [],
      voice: '',
      relationships: [],
      knowledge: { known: [], unknown: [] },
    },
    scene: {
      location: '',
      current_activity: '',
      current_goal: '',
      emotional_baseline: '',
      channel_stage: 'in_world_visitors',
      host_relationship: '',
      audience_relationship: '',
      adaptation_note: '',
      host_character_mapping: null,
      audience_character_mapping: null,
    },
    lore_entries: [],
    example_replies: [],
  }
}

const authed = { credentials: 'include' } as const
const mutationHeaders = {
  'Content-Type': 'application/json',
  'X-Niibot-Action': 'roleplay-settings',
} as const
const deleteHeaders = { 'X-Niibot-Action': 'roleplay-settings' } as const

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function parseRoleplayCharacterFile(text: string): RoleplayCharacterFile {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    throw new Error('無法讀取這個檔案，請選擇 Niibot 匯出的角色設定集')
  }
  const document = record(raw)
  if (
    !document ||
    document.format !== 'niibot.roleplay-character' ||
    document.format_version !== 1
  ) {
    throw new Error('這不是支援的 Niibot 角色設定集')
  }
  const manifest = record(document.manifest)
  const roleplayPackage = record(document.package)
  const world = record(roleplayPackage?.world)
  const character = record(roleplayPackage?.character)
  const preview = record(document.compiled_preview)
  if (
    !manifest ||
    typeof manifest.name !== 'string' ||
    manifest.schema_version !== 1 ||
    manifest.compiler_version !== 1 ||
    typeof manifest.content_digest !== 'string' ||
    !roleplayPackage ||
    !world ||
    typeof world.title !== 'string' ||
    typeof world.story_stage !== 'string' ||
    !character ||
    typeof character.name !== 'string' ||
    !Array.isArray(roleplayPackage.lore_entries) ||
    !preview ||
    typeof preview.capsule !== 'string' ||
    typeof preview.compact_capsule !== 'string'
  ) {
    throw new Error('角色設定集內容不完整，請重新匯出後再試')
  }
  return raw as RoleplayCharacterFile
}

function exportedFilename(disposition: string | null): string {
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      // Fall through to the ASCII filename.
    }
  }
  const ascii = disposition?.match(/filename="?([^";]+)"?/i)?.[1]
  return ascii || 'niibot-roleplay.json'
}

export async function exportRoleplayRevision(
  channelId: string,
  setId: string,
  revisionId: number
): Promise<RoleplayExportDownload> {
  let response: Response
  try {
    response = await apiFetch(
      API_ENDPOINTS.tenants.roleplayRevisionExport(channelId, setId, revisionId),
      authed
    )
  } catch {
    throw new ApiError({
      message: '網路連線出了問題，請檢查後再試',
      status: 0,
      code: NETWORK_ERROR,
    })
  }
  if (!response.ok) throw await parseApiError(response, '下載角色設定集失敗')
  return {
    blob: await response.blob(),
    filename: exportedFilename(response.headers.get('Content-Disposition')),
  }
}

export function importRoleplayCharacter(
  channelId: string,
  mode: RoleplayImportMode,
  character: RoleplayCharacterFile
): Promise<RoleplayImportResult> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplayImports(channelId),
    {
      method: 'POST',
      ...authed,
      headers: mutationHeaders,
      body: JSON.stringify({ mode, character }),
    },
    { fallback: '匯入角色設定集失敗' }
  )
}

export function listRoleplaySets(channelId: string): Promise<RoleplaySetSummary[]> {
  return apiJson(API_ENDPOINTS.tenants.roleplaySets(channelId), authed, {
    fallback: '載入故事角色失敗',
  })
}

export function getRoleplaySet(channelId: string, setId: string): Promise<RoleplaySet> {
  return apiJson(API_ENDPOINTS.tenants.roleplaySet(channelId, setId), authed, {
    fallback: '載入角色草稿失敗',
  })
}

export function createRoleplaySet(
  channelId: string,
  name: string,
  draft: RoleplayPackage
): Promise<RoleplaySet> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplaySets(channelId),
    {
      method: 'POST',
      ...authed,
      headers: mutationHeaders,
      body: JSON.stringify({ name, draft }),
    },
    { fallback: '建立故事角色失敗' }
  )
}

export function updateRoleplayDraft(
  channelId: string,
  setId: string,
  expectedDraftVersion: number,
  draft: RoleplayPackage,
  name?: string
): Promise<RoleplaySet> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplaySet(channelId, setId),
    {
      method: 'PATCH',
      ...authed,
      headers: mutationHeaders,
      body: JSON.stringify({
        expected_draft_version: expectedDraftVersion,
        draft,
        ...(name === undefined ? {} : { name }),
      }),
    },
    { fallback: '儲存角色草稿失敗' }
  )
}

export function publishRoleplayRevision(
  channelId: string,
  setId: string,
  expectedDraftVersion: number
): Promise<RoleplayRevision> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplayRevisions(channelId, setId),
    {
      method: 'POST',
      ...authed,
      headers: mutationHeaders,
      body: JSON.stringify({ expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '完成角色設定失敗' }
  )
}

export function activateRoleplayRevision(
  channelId: string,
  setId: string,
  revisionId: number
): Promise<AssistantMode> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplayActiveRevision(channelId, setId),
    {
      method: 'PUT',
      ...authed,
      headers: mutationHeaders,
      body: JSON.stringify({ revision_id: revisionId }),
    },
    { fallback: '切換故事角色失敗' }
  )
}

export function usePersonaMode(channelId: string): Promise<AssistantMode> {
  return apiJson(
    API_ENDPOINTS.tenants.activeRoleplay(channelId),
    { method: 'DELETE', ...authed, headers: deleteHeaders },
    { fallback: '切換說話風格失敗' }
  )
}

export function archiveRoleplaySet(channelId: string, setId: string): Promise<RoleplaySet> {
  return apiJson(
    API_ENDPOINTS.tenants.roleplaySet(channelId, setId),
    { method: 'DELETE', ...authed, headers: deleteHeaders },
    { fallback: '封存故事角色失敗' }
  )
}
