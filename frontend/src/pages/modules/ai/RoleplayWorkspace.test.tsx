import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/roleplay', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    listRoleplaySets: vi.fn(),
    getRoleplaySet: vi.fn(),
    createRoleplaySet: vi.fn(),
    updateRoleplayDraft: vi.fn(),
    publishRoleplayRevision: vi.fn(),
    activateRoleplayRevision: vi.fn(),
    archiveRoleplaySet: vi.fn(),
    exportRoleplayRevision: vi.fn(),
    importRoleplayCharacter: vi.fn(),
  }
})
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { ApiError } from '@/api/errors'
import {
  activateRoleplayRevision,
  createEmptyRoleplayPackage,
  createRoleplaySet,
  exportRoleplayRevision,
  importRoleplayCharacter,
  listRoleplaySets,
  publishRoleplayRevision,
  type RoleplayCharacterFile,
  type RoleplayPackage,
  type RoleplaySet,
  updateRoleplayDraft,
} from '@/api/roleplay'

import { RoleplayWizard } from './RoleplayWizard'
import { stepForFieldPath } from './roleplayWizardUtils'
import { RoleplayWorkspace } from './RoleplayWorkspace'

const NOW = '2026-09-20T10:00:00Z'

function validPackage(): RoleplayPackage {
  return {
    ...createEmptyRoleplayPackage(),
    name: '月港守望者',
    world: {
      ...createEmptyRoleplayPackage().world,
      title: '月港',
      canon_scope: '原創世界的港區篇',
      world_anchor: '被月潮包圍的港都，守望者負責維持夜間航路。',
      story_stage: '第一艘失蹤船返港後的夜晚',
    },
    character: {
      ...createEmptyRoleplayPackage().character,
      name: '拉娜',
      role: '月港的年輕守望者',
      motivation: '找出失蹤船返港的真相，同時保護仍在海上的居民。',
      stable_traits: ['沉著', '對弱者溫柔'],
      boundaries: ['不會透露尚未查明的港務祕密'],
      voice: '句子簡短沉穩，先回答，再在自然時帶到海港意象。',
      knowledge: { known: ['失蹤船已空船返港'], unknown: ['船員目前身在何處'] },
      relationships: [
        {
          subject: '希雅',
          role: '共同值夜的同伴',
          state: 'trusted',
          notes: '會交換港區情報',
        },
      ],
    },
    scene: {
      ...createEmptyRoleplayPackage().scene,
      location: '月港守望塔',
      current_activity: '整理返港空船留下的航海紀錄',
      current_goal: '確認下一個安全搜索範圍',
      emotional_baseline: '保持鎮定，但對失蹤船員感到擔心',
      host_relationship: '把實況主視為共同值夜的搭檔',
      audience_relationship: '把聊天室觀眾視為來守望塔交換消息的訪客',
    },
    lore_entries: [
      {
        subject: '月潮',
        aliases: ['潮汐'],
        content: '夜間會改變港區航路。',
        known_at_stage: true,
        contains_spoilers: false,
        priority: 80,
      },
    ],
  }
}

function roleplaySet(): RoleplaySet {
  return {
    id: 'set-1',
    name: '月港守望者',
    draft_version: 3,
    draft: validPackage(),
    published: {
      id: 40,
      revision_number: 1,
      schema_version: 2,
      compiler_version: 2,
      content_digest: 'digest',
      published_at: NOW,
    },
    archived_at: null,
    created_at: NOW,
    updated_at: NOW,
  }
}

function portableCharacter(overrides: Partial<RoleplayCharacterFile['manifest']> = {}) {
  const character: RoleplayCharacterFile = {
    format: 'niibot.roleplay-character',
    format_version: 1,
    manifest: {
      name: '月港守望者',
      exported_at: NOW,
      schema_version: 2,
      compiler_version: 2,
      content_digest: 'digest-from-file',
      ...overrides,
    },
    package: validPackage(),
    compiled_preview: {
      capsule: '完整摘要',
      compact_capsule: '輕量摘要',
    },
  }
  return new File([JSON.stringify(character)], '月港守望者.niibot-roleplay.json', {
    type: 'application/json',
  })
}

describe('RoleplayWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listRoleplaySets).mockResolvedValue([])
  })

  it('teaches the empty state and creates the draft after the first step', async () => {
    const user = userEvent.setup()
    const created = {
      ...roleplaySet(),
      published: null,
      draft_version: 1,
      draft: createEmptyRoleplayPackage(),
    }
    vi.mocked(createRoleplaySet).mockResolvedValue(created)

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    expect(await screen.findByText('還沒有故事角色')).toBeInTheDocument()
    expect(screen.getByText(/跟著七個步驟/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '匯入角色設定集' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '建立故事角色' }))
    expect(screen.getByRole('heading', { name: '作品與故事範圍' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('角色設定名稱'), '月港守望者')
    await user.type(screen.getByLabelText('作品或世界名稱'), '月港')
    await user.click(screen.getByRole('button', { name: '儲存並繼續' }))

    await waitFor(() => expect(createRoleplaySet).toHaveBeenCalledTimes(1))
    expect(createRoleplaySet).toHaveBeenCalledWith(
      'channel-a',
      '月港守望者',
      expect.objectContaining({ name: '月港守望者' })
    )
    expect(screen.getByRole('heading', { name: '人物小傳' })).toBeInTheDocument()
  })

  it('does not offer archive for the active published character', async () => {
    vi.mocked(listRoleplaySets).mockResolvedValue([roleplaySet()])

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="roleplay"
        activeRevisionId={40}
        onModeChange={vi.fn()}
      />
    )

    expect(await screen.findByText('使用中')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '封存' })).not.toBeInTheDocument()
  })

  it('explains the five-character limit and disables creating another set', async () => {
    vi.mocked(listRoleplaySets).mockResolvedValue(
      Array.from({ length: 5 }, (_, index) => ({
        ...roleplaySet(),
        id: `set-${index + 1}`,
        name: `角色 ${index + 1}`,
      }))
    )

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    expect(await screen.findByText(/已達 5 組上限/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立故事角色' })).toBeDisabled()
  })

  it('previews an imported character and opens a copied draft without changing runtime', async () => {
    const user = userEvent.setup()
    const copied = { ...roleplaySet(), id: 'copied-set', published: null }
    vi.mocked(importRoleplayCharacter).mockResolvedValue({
      mode: 'copy',
      reused: false,
      roleplay_set: copied,
      active_roleplay_revision_id: null,
    })
    const onModeChange = vi.fn()

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={onModeChange}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    await user.upload(screen.getByLabelText('選擇角色設定集'), portableCharacter())

    expect(await screen.findByText('拉娜')).toBeInTheDocument()
    expect(screen.getByText('月港')).toBeInTheDocument()
    expect(screen.getByText('第一艘失蹤船返港後的夜晚')).toBeInTheDocument()
    expect(screen.getByText('1 條背景條目')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '複製並修改' }))

    await waitFor(() => expect(importRoleplayCharacter).toHaveBeenCalledTimes(1))
    expect(importRoleplayCharacter).toHaveBeenCalledWith(
      'channel-a',
      'copy',
      expect.objectContaining({ format: 'niibot.roleplay-character' })
    )
    expect(onModeChange).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: '作品與故事範圍' })).toBeInTheDocument()
  })

  it('reuses the same published version when using an imported character', async () => {
    const user = userEvent.setup()
    vi.mocked(listRoleplaySets).mockResolvedValue([roleplaySet()])
    vi.mocked(importRoleplayCharacter).mockResolvedValue({
      mode: 'use',
      reused: true,
      roleplay_set: roleplaySet(),
      active_roleplay_revision_id: 40,
    })
    const onModeChange = vi.fn()

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={onModeChange}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    await user.upload(
      screen.getByLabelText('選擇角色設定集'),
      portableCharacter({ content_digest: 'digest' })
    )

    expect(await screen.findByText(/已有相同版本/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '使用這個角色' }))

    await waitFor(() => expect(onModeChange).toHaveBeenCalledWith('roleplay', 40))
    expect(importRoleplayCharacter).toHaveBeenCalledWith(
      'channel-a',
      'use',
      expect.objectContaining({ format: 'niibot.roleplay-character' })
    )
  })

  it('warns before downloading a published character and releases the browser URL', async () => {
    const user = userEvent.setup()
    vi.mocked(listRoleplaySets).mockResolvedValue([roleplaySet()])
    vi.mocked(exportRoleplayRevision).mockResolvedValue({
      blob: new Blob(['{}'], { type: 'application/json' }),
      filename: '月港守望者.niibot-roleplay.json',
    })
    const createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:roleplay-download')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    await user.click(await screen.findByRole('button', { name: '更多角色操作' }))
    await user.click(screen.getByRole('menuitem', { name: '下載設定集' }))

    expect(screen.getByText(/檔案包含完整作品範圍/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '確認下載設定集' }))

    await waitFor(() => expect(exportRoleplayRevision).toHaveBeenCalledTimes(1))
    expect(exportRoleplayRevision).toHaveBeenCalledWith('channel-a', 'set-1', 40)
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:roleplay-download')
    expect(toast.success).toHaveBeenCalledWith('角色設定集已下載')
  })

  it('rejects an oversized imported file before sending it', async () => {
    const user = userEvent.setup()

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    const oversized = new File([new Uint8Array(128 * 1024 + 1)], 'too-large.niibot-roleplay.json', {
      type: 'application/json',
    })
    await user.upload(screen.getByLabelText('選擇角色設定集'), oversized)

    expect(await screen.findByRole('alert')).toHaveTextContent('檔案大小不能超過 128 KB')
    expect(importRoleplayCharacter).not.toHaveBeenCalled()
  })

  it('keeps new imports disabled at the limit but allows an exact-version reuse', async () => {
    const user = userEvent.setup()
    vi.mocked(listRoleplaySets).mockResolvedValue(
      Array.from({ length: 5 }, (_, index) => ({
        ...roleplaySet(),
        id: `set-${index + 1}`,
        name: `角色 ${index + 1}`,
        published: {
          ...roleplaySet().published!,
          content_digest: index === 0 ? 'digest' : `digest-${index + 1}`,
        },
      }))
    )

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    await user.upload(screen.getByLabelText('選擇角色設定集'), portableCharacter())

    expect(await screen.findByText(/請先封存一組未使用的角色/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '複製並修改' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '使用這個角色' })).toBeDisabled()

    await user.upload(
      screen.getByLabelText('選擇角色設定集'),
      portableCharacter({ content_digest: 'digest' })
    )

    expect(await screen.findByText(/已有相同版本/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '複製並修改' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '使用這個角色' })).toBeEnabled()
  })

  it('keeps the import preview open with a useful error so the action can be retried', async () => {
    const user = userEvent.setup()
    vi.mocked(importRoleplayCharacter)
      .mockRejectedValueOnce(new Error('這份角色設定集版本目前不支援'))
      .mockResolvedValueOnce({
        mode: 'use',
        reused: false,
        roleplay_set: roleplaySet(),
        active_roleplay_revision_id: 40,
      })
    const onModeChange = vi.fn()

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={onModeChange}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    await user.upload(screen.getByLabelText('選擇角色設定集'), portableCharacter())
    await user.click(await screen.findByRole('button', { name: '使用這個角色' }))

    expect(await screen.findByText('這份角色設定集版本目前不支援')).toBeInTheDocument()
    expect(screen.getByText('拉娜')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '使用這個角色' }))
    await waitFor(() => expect(onModeChange).toHaveBeenCalledWith('roleplay', 40))
  })

  it('closes the import dialog with Escape and returns focus to its trigger', async () => {
    const user = userEvent.setup()

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    const trigger = await screen.findByRole('button', { name: '匯入角色設定集' })
    await user.click(trigger)
    expect(screen.getByRole('dialog', { name: '匯入角色設定集' })).toBeInTheDocument()

    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it('keeps the import dialog open while the selected action is still running', async () => {
    const user = userEvent.setup()
    let finishImport:
      ((result: Awaited<ReturnType<typeof importRoleplayCharacter>>) => void) | null = null
    vi.mocked(importRoleplayCharacter).mockReturnValue(
      new Promise(resolve => {
        finishImport = resolve
      })
    )

    render(
      <RoleplayWorkspace
        channelId="channel-a"
        assistantMode="persona"
        activeRevisionId={null}
        onModeChange={vi.fn()}
      />
    )

    await user.click(await screen.findByRole('button', { name: '匯入角色設定集' }))
    await user.upload(screen.getByLabelText('選擇角色設定集'), portableCharacter())
    await user.click(await screen.findByRole('button', { name: '使用這個角色' }))
    await user.keyboard('{Escape}')

    expect(screen.getByRole('dialog', { name: '匯入角色設定集' })).toBeInTheDocument()
    finishImport?.({
      mode: 'use',
      reused: false,
      roleplay_set: roleplaySet(),
      active_roleplay_revision_id: 40,
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})

describe('RoleplayWizard', () => {
  it('maps server validation paths back to the authoring step that owns them', () => {
    expect(stepForFieldPath('world.story_stage')).toBe(2)
    expect(stepForFieldPath('character.relationships.0.subject')).toBe(3)
    expect(stepForFieldPath('scene.location')).toBe(2)
    expect(stepForFieldPath('scene.host_relationship')).toBe(4)
    expect(stepForFieldPath('package.lore_entries.0.content')).toBe(5)
    expect(stepForFieldPath('lore_entries.0.known_at_stage')).toBe(5)
    expect(stepForFieldPath('example_replies.0')).toBe(5)
    expect(stepForFieldPath('character.signature_phrases.0.text')).toBe(5)
  })

  it('saves, publishes, and activates in order without calling a model preview', async () => {
    const user = userEvent.setup()
    const initial = roleplaySet()
    const saved = { ...initial, draft_version: 4 }
    vi.mocked(updateRoleplayDraft).mockResolvedValue(saved)
    vi.mocked(publishRoleplayRevision).mockResolvedValue({
      ...initial.published!,
      id: 41,
      roleplay_set_id: initial.id,
      package: initial.draft,
      capsule: '完整摘要',
      compact_capsule: '輕量摘要',
    })
    vi.mocked(activateRoleplayRevision).mockResolvedValue({
      assistant_mode: 'roleplay',
      active_roleplay_revision_id: 41,
    })
    const onModeChange = vi.fn()

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={initial}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onModeChange={onModeChange}
      />
    )

    for (let step = 0; step < 6; step++) {
      await user.click(screen.getByRole('button', { name: '儲存並繼續' }))
    }
    expect(screen.getByRole('heading', { name: '最後檢查' })).toBeInTheDocument()
    expect(screen.getByText('船員目前身在何處')).toBeInTheDocument()
    expect(screen.getByText(/希雅/)).toBeInTheDocument()
    expect(screen.getByText('月潮')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '完成並使用' }))

    await waitFor(() => expect(activateRoleplayRevision).toHaveBeenCalledTimes(1))
    expect(publishRoleplayRevision).toHaveBeenCalledWith('channel-a', 'set-1', 4)
    expect(activateRoleplayRevision).toHaveBeenCalledWith('channel-a', 'set-1', 41)
    expect(onModeChange).toHaveBeenCalledWith('roleplay', 41)
  })

  it('retries only activation when publishing succeeded but activation failed', async () => {
    const user = userEvent.setup()
    const initial = roleplaySet()
    const saved = { ...initial, draft_version: 4 }
    vi.mocked(updateRoleplayDraft).mockResolvedValue(saved)
    vi.mocked(publishRoleplayRevision).mockResolvedValue({
      ...initial.published!,
      id: 41,
      roleplay_set_id: initial.id,
      package: initial.draft,
      capsule: '完整摘要',
      compact_capsule: '輕量摘要',
    })
    vi.mocked(activateRoleplayRevision)
      .mockRejectedValueOnce(
        new ApiError({ message: '暫時無法啟用', status: 502, code: 'HTTP.502' })
      )
      .mockResolvedValueOnce({
        assistant_mode: 'roleplay',
        active_roleplay_revision_id: 41,
      })

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={initial}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onModeChange={vi.fn()}
      />
    )

    for (let step = 0; step < 6; step++) {
      await user.click(screen.getByRole('button', { name: '儲存並繼續' }))
    }
    await user.click(screen.getByRole('button', { name: '完成並使用' }))

    expect(await screen.findByRole('button', { name: '再次嘗試使用' })).toBeInTheDocument()
    expect(publishRoleplayRevision).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: '再次嘗試使用' }))

    await waitFor(() => expect(activateRoleplayRevision).toHaveBeenCalledTimes(2))
    expect(publishRoleplayRevision).toHaveBeenCalledTimes(1)
  })

  it('returns to the first invalid authoring step when publish validation fails', async () => {
    const user = userEvent.setup()
    const initial = roleplaySet()
    vi.mocked(updateRoleplayDraft).mockResolvedValue({ ...initial, draft_version: 4 })
    vi.mocked(publishRoleplayRevision).mockRejectedValue(
      new ApiError({
        message: '角色設定尚未完整',
        status: 422,
        code: 'ROLEPLAY.INVALID',
        fields: { 'scene.location': '請填寫目前地點' },
      })
    )

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={initial}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onModeChange={vi.fn()}
      />
    )

    for (let step = 0; step < 6; step++) {
      await user.click(screen.getByRole('button', { name: '儲存並繼續' }))
    }
    await user.click(screen.getByRole('button', { name: '完成並使用' }))

    expect(await screen.findByRole('heading', { name: '故事時間點與當前場景' })).toBeInTheDocument()
    expect(screen.getByText('請填寫目前地點')).toBeInTheDocument()
  })

  it('warns before discarding an unsaved authoring step', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const onCancel = vi.fn()

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={roleplaySet()}
        onCancel={onCancel}
        onSaved={vi.fn()}
        onModeChange={vi.fn()}
      />
    )

    await user.type(screen.getByLabelText('角色設定名稱'), '修改')
    await user.click(screen.getByRole('button', { name: '回到角色清單' }))
    expect(onCancel).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '回到角色清單' }))
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('does not overwrite a draft after an optimistic version conflict', async () => {
    const user = userEvent.setup()
    vi.mocked(updateRoleplayDraft).mockRejectedValue(
      new ApiError({
        message: '草稿已更新',
        status: 409,
        code: 'ROLEPLAY.DRAFT_CONFLICT',
      })
    )

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={roleplaySet()}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onModeChange={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: '儲存並繼續' }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        '這份角色設定已在其他頁面更新。請回到角色清單並重新開啟。'
      )
    )
    expect(screen.getByRole('heading', { name: '作品與故事範圍' })).toBeInTheDocument()
  })

  it('keeps literary authoring terms while explaining each step in plain language', async () => {
    const user = userEvent.setup()
    const initial = roleplaySet()
    vi.mocked(updateRoleplayDraft).mockResolvedValue({ ...initial, draft_version: 4 })

    render(
      <RoleplayWizard
        channelId="channel-a"
        initialSet={initial}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onModeChange={vi.fn()}
      />
    )

    expect(screen.getByText(/先決定角色來自哪個作品/)).toBeInTheDocument()
    const headings = [
      '人物小傳',
      '故事時間點與當前場景',
      '人物關係與角色所知',
      '聊天室舞台',
      '背景條目與角色台詞',
      '最後檢查',
    ]
    for (const heading of headings) {
      await user.click(screen.getByRole('button', { name: '儲存並繼續' }))
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
      if (heading === '背景條目與角色台詞') {
        expect(screen.getByText('角色招牌語句')).toBeInTheDocument()
        expect(screen.getByText(/只在情境自然吻合時偶爾使用/)).toBeInTheDocument()
        await user.click(screen.getByRole('button', { name: '新增招牌語句' }))
        expect(screen.getByLabelText('招牌語句 1')).toBeInTheDocument()
        expect(screen.getByLabelText('適合在什麼時候說 1')).toBeInTheDocument()
        expect(screen.getByLabelText('使用方式 1')).toBeInTheDocument()
      }
    }

    expect(screen.getByText(/只整理你填過的內容/)).toBeInTheDocument()
    expect(screen.getByText('要求跳出設定')).toBeInTheDocument()
    expect(screen.queryByText('角色劫持')).not.toBeInTheDocument()
  })
})
