import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import {
  activateRoleplayRevision,
  archiveRoleplaySet,
  createEmptyRoleplayPackage,
  createRoleplaySet,
  exportRoleplayRevision,
  getRoleplaySet,
  importRoleplayCharacter,
  listRoleplaySets,
  parseRoleplayCharacterFile,
  publishRoleplayRevision,
  updateRoleplayDraft,
  usePersonaMode,
} from './roleplay'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('role-play API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('builds a strict blank authoring document', () => {
    const draft = createEmptyRoleplayPackage()

    expect(draft).toEqual({
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
    })
  })

  it('keeps reads tenant-scoped and every mutation preflighted', async () => {
    const draft = createEmptyRoleplayPackage()
    draft.character.relationships = [
      { subject: '希雅', role: '共同值夜的同伴', state: 'trusted', notes: '彼此會交換情報' },
    ]
    const set = { id: 'set-1', name: '月港守望者', draft_version: 1, draft }
    const revision = { id: 41 }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(set))
      .mockResolvedValueOnce(jsonResponse(set, 201))
      .mockResolvedValueOnce(jsonResponse({ ...set, draft_version: 2 }))
      .mockResolvedValueOnce(jsonResponse(revision, 201))
      .mockResolvedValueOnce(
        jsonResponse({ assistant_mode: 'roleplay', active_roleplay_revision_id: 41 })
      )
      .mockResolvedValueOnce(
        jsonResponse({ assistant_mode: 'persona', active_roleplay_revision_id: null })
      )
      .mockResolvedValueOnce(jsonResponse(set))

    await listRoleplaySets('channel/a')
    await getRoleplaySet('channel/a', 'set-1')
    await createRoleplaySet('channel/a', '月港守望者', draft)
    await updateRoleplayDraft('channel/a', 'set-1', 1, draft, '月港守望者')
    await publishRoleplayRevision('channel/a', 'set-1', 2)
    await activateRoleplayRevision('channel/a', 'set-1', 41)
    await usePersonaMode('channel/a')
    await archiveRoleplaySet('channel/a', 'set-1')

    expect(fetchMock.mock.calls.map(call => requestUrl(call[0]).pathname)).toEqual([
      '/api/tenants/channel%2Fa/roleplay-sets',
      '/api/tenants/channel%2Fa/roleplay-sets/set-1',
      '/api/tenants/channel%2Fa/roleplay-sets',
      '/api/tenants/channel%2Fa/roleplay-sets/set-1',
      '/api/tenants/channel%2Fa/roleplay-sets/set-1/revisions',
      '/api/tenants/channel%2Fa/roleplay-sets/set-1/active-revision',
      '/api/tenants/channel%2Fa/active-roleplay',
      '/api/tenants/channel%2Fa/roleplay-sets/set-1',
    ])
    for (const call of fetchMock.mock.calls.slice(2)) {
      expect((call[1]?.headers as Record<string, string>)['X-Niibot-Action']).toBe(
        'roleplay-settings'
      )
    }
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toMatchObject({
      draft: {
        character: {
          relationships: [{ state: 'trusted' }],
        },
      },
    })
  })

  it('parses only the portable fields needed for a safe import preview', () => {
    const parsed = parseRoleplayCharacterFile(
      JSON.stringify({
        format: 'niibot.roleplay-character',
        format_version: 1,
        manifest: {
          name: '月港守望者',
          exported_at: '2026-09-20T10:00:00Z',
          schema_version: 1,
          compiler_version: 1,
          content_digest: 'a'.repeat(64),
        },
        package: {
          ...createEmptyRoleplayPackage(),
          world: {
            ...createEmptyRoleplayPackage().world,
            title: '月港紀事',
            story_stage: '潮汐祭前三日',
          },
          character: {
            ...createEmptyRoleplayPackage().character,
            name: '拉娜',
          },
        },
        compiled_preview: { capsule: '完整摘要', compact_capsule: '精簡摘要' },
      })
    )

    expect(parsed.manifest.name).toBe('月港守望者')
    expect(parsed.package.character.name).toBe('拉娜')
    expect(parsed.package.world.story_stage).toBe('潮汐祭前三日')
  })

  it('rejects malformed or unsupported files before showing an import preview', () => {
    expect(() => parseRoleplayCharacterFile('{bad json')).toThrow('無法讀取')
    expect(() =>
      parseRoleplayCharacterFile(
        JSON.stringify({ format: 'other', format_version: 1, manifest: {}, package: {} })
      )
    ).toThrow('不是支援的 Niibot 角色設定集')
  })

  it('downloads an exact revision and imports through the tenant boundary', async () => {
    const portable = {
      format: 'niibot.roleplay-character' as const,
      format_version: 1 as const,
      manifest: {
        name: '月港守望者',
        exported_at: '2026-09-20T10:00:00Z',
        schema_version: 1,
        compiler_version: 1,
        content_digest: 'a'.repeat(64),
      },
      package: createEmptyRoleplayPackage(),
      compiled_preview: { capsule: '完整摘要', compact_capsule: '精簡摘要' },
    }
    const imported = {
      mode: 'copy',
      reused: false,
      roleplay_set: { id: 'set-2', name: '月港守望者', draft_version: 1 },
      active_roleplay_revision_id: null,
    }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify(portable), {
          status: 200,
          headers: {
            'Content-Type': 'application/vnd.niibot.roleplay-character+json',
            'Content-Disposition':
              'attachment; filename="niibot-roleplay.json"; filename*=UTF-8\'\'%E6%9C%88%E6%B8%AF.niibot-roleplay.json',
          },
        })
      )
      .mockResolvedValueOnce(jsonResponse(imported))

    const download = await exportRoleplayRevision('channel/a', 'set-1', 41)
    await importRoleplayCharacter('channel/a', 'copy', portable)

    expect(download.filename).toBe('月港.niibot-roleplay.json')
    expect(await download.blob.text()).toContain('niibot.roleplay-character')
    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(
      '/api/tenants/channel%2Fa/roleplay-sets/set-1/revisions/41/export'
    )
    expect(requestUrl(fetchMock.mock.calls[1][0]).pathname).toBe(
      '/api/tenants/channel%2Fa/roleplay-imports'
    )
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      headers: expect.objectContaining({ 'X-Niibot-Action': 'roleplay-settings' }),
    })
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      mode: 'copy',
      character: portable,
    })
  })
})
