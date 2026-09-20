import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/api/errors'
import {
  activateRoleplayRevision,
  createEmptyRoleplayPackage,
  createRoleplaySet,
  publishRoleplayRevision,
  type RoleplayLoreEntry,
  type RoleplayPackage,
  type RoleplayRelationship,
  type RoleplaySet,
  updateRoleplayDraft,
} from '@/api/roleplay'
import { Icon, Spinner } from '@/components/primitives'
import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Separator,
  Switch,
  Textarea,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'
import { cn } from '@/lib/utils'

import { stepForFieldPath } from './roleplayWizardUtils'

const STEPS = [
  '作品與故事範圍',
  '人物小傳',
  '故事時間點與當前場景',
  '人物關係與角色所知',
  '聊天室舞台',
  '背景條目與說話示例',
  '最後檢查',
] as const

const RELATIONSHIP_STATE_LABELS: Record<RoleplayRelationship['state'], string> = {
  unfamiliar: '不熟悉',
  guarded: '有戒心',
  familiar: '熟悉',
  trusted: '信任',
  hostile: '敵對',
  intimate: '親密',
}

type AssistantMode = 'persona' | 'roleplay'
type FieldErrors = Record<string, string>

interface RoleplayWizardProps {
  channelId: string
  initialSet: RoleplaySet | null
  onCancel: () => void
  onSaved: (roleplaySet: RoleplaySet) => void
  onModeChange: (mode: AssistantMode, revisionId: number | null) => void
}

function splitAliases(value: string): string[] {
  return value
    .split(/[，,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function FieldError({ path, errors }: { path: string; errors: FieldErrors }) {
  const message = errors[path]
  if (!message) return null
  return (
    <p className="text-label text-destructive" role="alert">
      {message}
    </p>
  )
}

function StringListEditor({
  label,
  description,
  values,
  maxItems,
  maxLength,
  addLabel,
  onChange,
}: {
  label: string
  description: string
  values: string[]
  maxItems: number
  maxLength: number
  addLabel: string
  onChange: (values: string[]) => void
}) {
  return (
    <div className="flex flex-col gap-element">
      <div>
        <Label>{label}</Label>
        <p className="mt-1 text-label text-muted-foreground">{description}</p>
      </div>
      {values.map((value, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            aria-label={`${label} ${index + 1}`}
            value={value}
            maxLength={maxLength}
            onChange={event => {
              const next = [...values]
              next[index] = event.target.value
              onChange(next)
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`移除${label} ${index + 1}`}
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          >
            <Icon icon="fa-solid fa-trash" />
          </Button>
        </div>
      ))}
      {values.length < maxItems && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() => onChange([...values, ''])}
        >
          <Icon icon="fa-solid fa-plus" className="mr-1.5" />
          {addLabel}
        </Button>
      )}
    </div>
  )
}

function draftSignature(name: string, draft: RoleplayPackage): string {
  return JSON.stringify({ name: name.trim(), draft })
}

function stepZeroErrors(name: string, draft: RoleplayPackage): FieldErrors {
  const errors: FieldErrors = {}
  if (!name.trim()) errors.name = '請替這份角色設定取一個名稱'
  if (!draft.world.title.trim()) errors['world.title'] = '請填寫作品或世界名稱'
  return errors
}

export function RoleplayWizard({
  channelId,
  initialSet,
  onCancel,
  onSaved,
  onModeChange,
}: RoleplayWizardProps) {
  const [step, setStep] = useState(0)
  const [setId, setSetId] = useState<string | null>(initialSet?.id ?? null)
  const [draftVersion, setDraftVersion] = useState(initialSet?.draft_version ?? 1)
  const [setName, setSetName] = useState(initialSet?.name ?? '')
  const [draft, setDraft] = useState<RoleplayPackage>(
    initialSet?.draft ?? createEmptyRoleplayPackage()
  )
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [lastSavedSignature, setLastSavedSignature] = useState(() =>
    draftSignature(initialSet?.name ?? '', initialSet?.draft ?? createEmptyRoleplayPackage())
  )
  const [pendingRevision, setPendingRevision] = useState<{
    setId: string
    revisionId: number
    signature: string
  } | null>(null)

  const currentTitle = STEPS[step]
  const progress = Math.round(((step + 1) / STEPS.length) * 100)
  const currentSignature = draftSignature(setName, draft)
  const hasUnsavedChanges = currentSignature !== lastSavedSignature
  const canRetryActivation = pendingRevision?.signature === currentSignature

  useEffect(() => {
    if (!hasUnsavedChanges) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [hasUnsavedChanges])

  const reviewRows = useMemo(
    () => [
      ['作品範圍', `${draft.world.title || '尚未填寫'}・${draft.world.canon_scope || '範圍未填'}`],
      ['故事時間點', draft.world.story_stage || '尚未填寫'],
      ['人物核心', `${draft.character.name || '尚未命名'}・${draft.character.role || '定位未填'}`],
      [
        '當前場景',
        `${draft.scene.location || '地點未填'}・${draft.scene.current_activity || '行動未填'}`,
      ],
      ['角色知道', draft.character.knowledge.known.join('、') || '未列出'],
      ['角色不知道', draft.character.knowledge.unknown.join('、') || '未列出'],
      [
        '人物關係',
        draft.character.relationships
          .map(item => `${item.subject || '未命名'}（${RELATIONSHIP_STATE_LABELS[item.state]}）`)
          .join('、') || '未列出',
      ],
      ['角色與聊天室', draft.scene.audience_relationship || '尚未填寫'],
      [
        '背景條目',
        draft.lore_entries
          .map(item => item.subject)
          .filter(Boolean)
          .join('、') || '未列出',
      ],
    ],
    [draft]
  )

  function replaceWorld(patch: Partial<RoleplayPackage['world']>) {
    setDraft(current => ({ ...current, world: { ...current.world, ...patch } }))
  }

  function replaceCharacter(patch: Partial<RoleplayPackage['character']>) {
    setDraft(current => ({ ...current, character: { ...current.character, ...patch } }))
  }

  function replaceScene(patch: Partial<RoleplayPackage['scene']>) {
    setDraft(current => ({ ...current, scene: { ...current.scene, ...patch } }))
  }

  async function persistDraft(): Promise<RoleplaySet> {
    if (setId === null) {
      const created = await createRoleplaySet(channelId, setName.trim(), draft)
      setSetId(created.id)
      setDraftVersion(created.draft_version)
      setLastSavedSignature(currentSignature)
      onSaved(created)
      return created
    }
    const saved = await updateRoleplayDraft(channelId, setId, draftVersion, draft, setName.trim())
    setDraftVersion(saved.draft_version)
    setLastSavedSignature(currentSignature)
    onSaved(saved)
    return saved
  }

  async function handleContinue() {
    if (step === 0) {
      const nextErrors = stepZeroErrors(setName, draft)
      if (Object.keys(nextErrors).length > 0) {
        setErrors(nextErrors)
        return
      }
    }
    setSaving(true)
    setErrors({})
    try {
      await persistDraft()
      setStep(current => Math.min(current + 1, STEPS.length - 1))
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error('這份角色設定已在其他頁面更新。請回到角色清單並重新開啟。')
      } else {
        toastApiError(error, '儲存失敗，請重試')
      }
    } finally {
      setSaving(false)
    }
  }

  async function handleFinish() {
    setSaving(true)
    setErrors({})
    let activationTarget = canRetryActivation ? pendingRevision : null
    try {
      if (activationTarget === null) {
        const saved = await persistDraft()
        const revision = await publishRoleplayRevision(channelId, saved.id, saved.draft_version)
        activationTarget = {
          setId: saved.id,
          revisionId: revision.id,
          signature: currentSignature,
        }
        setPendingRevision(activationTarget)
      }
      const mode = await activateRoleplayRevision(
        channelId,
        activationTarget.setId,
        activationTarget.revisionId
      )
      setPendingRevision(null)
      onModeChange(mode.assistant_mode, mode.active_roleplay_revision_id)
      toast.success('故事角色已完成並開始使用')
      onCancel()
    } catch (error) {
      if (error instanceof ApiError && error.fields) {
        setErrors(error.fields)
        setStep(Math.min(...Object.keys(error.fields).map(stepForFieldPath)))
        toast.error('還有內容需要補寫')
      } else if (error instanceof ApiError && error.status === 409) {
        toast.error('這份角色設定已在其他頁面更新。請回到角色清單並重新開啟。')
      } else if (activationTarget !== null) {
        toastApiError(error, '角色已完成，但尚未開始使用；請再試一次')
      } else {
        toastApiError(error, '完成角色失敗，請重試')
      }
    } finally {
      setSaving(false)
    }
  }

  function requestCancel() {
    if (
      hasUnsavedChanges &&
      !window.confirm('這一步還有未儲存的內容。確定要離開並放棄這些變更嗎？')
    ) {
      return
    }
    onCancel()
  }

  return (
    <Card>
      <CardHeader className="border-b">
        <div className="min-w-0">
          <p className="text-label text-muted-foreground">
            第 {step + 1} 步，共 {STEPS.length} 步
          </p>
          <CardTitle>
            <h2>{currentTitle}</h2>
          </CardTitle>
        </div>
        <Button variant="ghost" size="sm" onClick={requestCancel} disabled={saving}>
          回到角色清單
        </Button>
        <div
          className="col-span-full h-1.5 overflow-hidden rounded-full bg-muted"
          aria-label={`建立進度 ${progress}%`}
        >
          <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
        </div>
      </CardHeader>
      <div className="grid lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="角色建立步驟" className="hidden border-r p-card lg:block">
          <ol className="space-y-1">
            {STEPS.map((title, index) => (
              <li key={title}>
                <button
                  type="button"
                  onClick={() => index <= step && setStep(index)}
                  disabled={index > step || saving}
                  className={cn(
                    'w-full rounded-md px-3 py-2 text-left text-sub transition-colors',
                    index === step
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                    index > step && 'cursor-not-allowed opacity-50'
                  )}
                >
                  {title}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <CardContent className="flex min-w-0 flex-col gap-section p-card">
          {step === 0 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                先決定角色來自哪個作品，以及這次要演到哪段故事。這會限制角色知道的事，避免提到後續劇情或出戲。
              </p>
              <div className="grid gap-section sm:grid-cols-2">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="roleplay-set-name">角色設定名稱</Label>
                  <Input
                    id="roleplay-set-name"
                    value={setName}
                    maxLength={100}
                    aria-invalid={Boolean(errors.name)}
                    onChange={event => {
                      const value = event.target.value
                      setSetName(value)
                      setDraft(current => ({ ...current, name: value }))
                    }}
                    placeholder="例如：月港守望者・拉娜"
                  />
                  <FieldError path="name" errors={errors} />
                </div>
                <div className="flex flex-col gap-element">
                  <Label htmlFor="world-title">作品或世界名稱</Label>
                  <Input
                    id="world-title"
                    value={draft.world.title}
                    maxLength={100}
                    aria-invalid={Boolean(errors['world.title'])}
                    onChange={event => replaceWorld({ title: event.target.value })}
                    placeholder="原創世界或作品名稱"
                  />
                  <FieldError path="world.title" errors={errors} />
                </div>
              </div>
              <div className="grid gap-section sm:grid-cols-2">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="source-kind">作品來源</Label>
                  <select
                    id="source-kind"
                    className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                    value={draft.world.source_kind}
                    onChange={event => {
                      const original = event.target.value === 'original'
                      replaceWorld({
                        source_kind: original ? 'original' : 'existing_work',
                        canon_mode: original ? 'original' : 'canon',
                      })
                    }}
                  >
                    <option value="original">原創設定</option>
                    <option value="existing_work">既有作品</option>
                  </select>
                </div>
                <div className="flex flex-col gap-element">
                  <Label htmlFor="canon-mode">與原作的關係</Label>
                  <select
                    id="canon-mode"
                    className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                    value={draft.world.canon_mode}
                    disabled={draft.world.source_kind === 'original'}
                    onChange={event =>
                      replaceWorld({
                        canon_mode: event.target.value as 'canon' | 'alternate_universe',
                      })
                    }
                  >
                    {draft.world.source_kind === 'original' && (
                      <option value="original">原創設定</option>
                    )}
                    <option value="canon">遵循原作</option>
                    <option value="alternate_universe">平行設定</option>
                  </select>
                </div>
              </div>
              <div className="flex flex-col gap-element">
                <Label htmlFor="canon-scope">作品範圍</Label>
                <Textarea
                  id="canon-scope"
                  value={draft.world.canon_scope}
                  maxLength={500}
                  rows={2}
                  onChange={event => replaceWorld({ canon_scope: event.target.value })}
                  placeholder="例如：只採用動畫第一季第 1–11 集，不包含後續劇情"
                />
                <FieldError path="world.canon_scope" errors={errors} />
              </div>
              <div className="flex flex-col gap-element">
                <Label htmlFor="world-anchor">世界背景摘要</Label>
                <Textarea
                  id="world-anchor"
                  value={draft.world.world_anchor}
                  maxLength={1200}
                  rows={4}
                  onChange={event => replaceWorld({ world_anchor: event.target.value })}
                  placeholder="只寫理解角色所必需的世界規則、組織與衝突"
                />
                <FieldError path="world.world_anchor" errors={errors} />
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                寫下角色長期不變的核心。當下的情緒與態度，會在後面的場景和人物關係中補充。
              </p>
              <div className="grid gap-section sm:grid-cols-2">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="character-name">角色姓名</Label>
                  <Input
                    id="character-name"
                    value={draft.character.name}
                    maxLength={80}
                    onChange={event => replaceCharacter({ name: event.target.value })}
                  />
                  <FieldError path="character.name" errors={errors} />
                </div>
                <div className="flex flex-col gap-element">
                  <Label htmlFor="character-role">人物定位</Label>
                  <Input
                    id="character-role"
                    value={draft.character.role}
                    maxLength={500}
                    onChange={event => replaceCharacter({ role: event.target.value })}
                    placeholder="她在故事中的身分與責任"
                  />
                  <FieldError path="character.role" errors={errors} />
                </div>
              </div>
              <div className="flex flex-col gap-element">
                <Label htmlFor="motivation">此刻最在意的事</Label>
                <Textarea
                  id="motivation"
                  value={draft.character.motivation}
                  maxLength={500}
                  rows={3}
                  onChange={event => replaceCharacter({ motivation: event.target.value })}
                />
                <FieldError path="character.motivation" errors={errors} />
              </div>
              <StringListEditor
                label="穩定性格"
                description="選 1–8 個在多數情境下都成立的特質。"
                values={draft.character.stable_traits}
                maxItems={8}
                maxLength={120}
                addLabel="新增性格"
                onChange={stable_traits => replaceCharacter({ stable_traits })}
              />
              <FieldError path="character.stable_traits" errors={errors} />
              <StringListEditor
                label="不會做的事"
                description="至少一項，寫出會讓角色出戲的行為邊界。"
                values={draft.character.boundaries}
                maxItems={10}
                maxLength={200}
                addLabel="新增界線"
                onChange={boundaries => replaceCharacter({ boundaries })}
              />
              <FieldError path="character.boundaries" errors={errors} />
              <div className="flex flex-col gap-element">
                <Label htmlFor="voice">說話方式</Label>
                <Textarea
                  id="voice"
                  value={draft.character.voice}
                  maxLength={800}
                  rows={4}
                  onChange={event => replaceCharacter({ voice: event.target.value })}
                  placeholder="句子長短、節奏、禮貌程度，以及什麼時候才會顯露情緒"
                />
                <FieldError path="character.voice" errors={errors} />
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                先選定這次故事發生在哪個時間點，再寫角色眼前的地點、行動與目標。
              </p>
              <div className="flex flex-col gap-element">
                <Label htmlFor="story-stage">故事時間點</Label>
                <Textarea
                  id="story-stage"
                  value={draft.world.story_stage}
                  maxLength={500}
                  rows={2}
                  onChange={event => replaceWorld({ story_stage: event.target.value })}
                />
                <FieldError path="world.story_stage" errors={errors} />
              </div>
              <div className="grid gap-section sm:grid-cols-2">
                {(
                  [
                    ['location', '目前地點'],
                    ['current_activity', '正在做的事'],
                    ['current_goal', '當前目標'],
                    ['emotional_baseline', '情緒基調'],
                  ] as const
                ).map(([field, label]) => (
                  <div key={field} className="flex flex-col gap-element">
                    <Label htmlFor={field}>{label}</Label>
                    <Textarea
                      id={field}
                      value={draft.scene[field]}
                      maxLength={500}
                      rows={2}
                      onChange={event => replaceScene({ [field]: event.target.value })}
                    />
                    <FieldError path={`scene.${field}`} errors={errors} />
                  </div>
                ))}
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                人物關係會改變角色的態度。也請列出角色此刻知道與不知道的事，避免帶出後續劇情。
              </p>
              <div className="flex flex-col gap-element">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <Label>人物關係</Label>
                    <p className="mt-1 text-label text-muted-foreground">
                      只加入這個故事時間點會用到的人物。
                    </p>
                  </div>
                  {draft.character.relationships.length < 20 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        replaceCharacter({
                          relationships: [
                            ...draft.character.relationships,
                            { subject: '', role: '', state: 'familiar', notes: '' },
                          ],
                        })
                      }
                    >
                      新增關係
                    </Button>
                  )}
                </div>
                {draft.character.relationships.map((relationship, index) => (
                  <div key={index} className="grid gap-2 rounded-md bg-muted/50 p-3 sm:grid-cols-2">
                    <Input
                      aria-label={`關係人物 ${index + 1}`}
                      value={relationship.subject}
                      placeholder="人物姓名"
                      onChange={event => {
                        const next = [...draft.character.relationships]
                        next[index] = { ...relationship, subject: event.target.value }
                        replaceCharacter({ relationships: next })
                      }}
                    />
                    <Input
                      aria-label={`關係定位 ${index + 1}`}
                      value={relationship.role}
                      placeholder="例如：信任的同伴"
                      onChange={event => {
                        const next = [...draft.character.relationships]
                        next[index] = { ...relationship, role: event.target.value }
                        replaceCharacter({ relationships: next })
                      }}
                    />
                    <select
                      aria-label={`關係狀態 ${index + 1}`}
                      className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                      value={relationship.state}
                      onChange={event => {
                        const next = [...draft.character.relationships]
                        next[index] = {
                          ...relationship,
                          state: event.target.value as RoleplayRelationship['state'],
                        }
                        replaceCharacter({ relationships: next })
                      }}
                    >
                      <option value="unfamiliar">不熟悉</option>
                      <option value="guarded">有戒心</option>
                      <option value="familiar">熟悉</option>
                      <option value="trusted">信任</option>
                      <option value="hostile">敵對</option>
                      <option value="intimate">親密</option>
                    </select>
                    <div className="flex gap-2">
                      <Input
                        aria-label={`關係補充 ${index + 1}`}
                        value={relationship.notes}
                        placeholder="目前相處狀態（選填）"
                        onChange={event => {
                          const next = [...draft.character.relationships]
                          next[index] = { ...relationship, notes: event.target.value }
                          replaceCharacter({ relationships: next })
                        }}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`移除關係 ${index + 1}`}
                        onClick={() =>
                          replaceCharacter({
                            relationships: draft.character.relationships.filter(
                              (_, itemIndex) => itemIndex !== index
                            ),
                          })
                        }
                      >
                        <Icon icon="fa-solid fa-trash" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <StringListEditor
                label="角色知道的事"
                description="這個時間點已經親眼見過、被告知或能合理推知的事。"
                values={draft.character.knowledge.known}
                maxItems={30}
                maxLength={300}
                addLabel="新增已知資訊"
                onChange={known =>
                  replaceCharacter({ knowledge: { ...draft.character.knowledge, known } })
                }
              />
              <StringListEditor
                label="角色不知道的事"
                description="後續劇情、他人的祕密，或目前無從得知的答案。"
                values={draft.character.knowledge.unknown}
                maxItems={30}
                maxLength={300}
                addLabel="新增未知資訊"
                onChange={unknown =>
                  replaceCharacter({ knowledge: { ...draft.character.knowledge, unknown } })
                }
              />
              <FieldError path="character.knowledge" errors={errors} />
            </>
          )}

          {step === 4 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                設定角色如何看待實況主與觀眾。觀眾仍是聊天室中的自己，不會被當成某個原作人物。
              </p>
              <div className="flex flex-col gap-element">
                <Label htmlFor="channel-stage">聊天室舞台</Label>
                <select
                  id="channel-stage"
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                  value={draft.scene.channel_stage}
                  onChange={event => {
                    const channel_stage = event.target
                      .value as RoleplayPackage['scene']['channel_stage']
                    replaceScene({
                      channel_stage,
                      host_character_mapping:
                        channel_stage === 'chat_adapted'
                          ? null
                          : draft.scene.host_character_mapping,
                    })
                  }}
                >
                  <option value="in_world_visitors">觀眾來到故事世界</option>
                  <option value="chat_adapted">角色來到直播聊天室</option>
                  <option value="cross_world">兩個世界互相連通</option>
                </select>
              </div>
              <div className="grid gap-section sm:grid-cols-2">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="host-relationship">角色如何看待實況主</Label>
                  <Textarea
                    id="host-relationship"
                    value={draft.scene.host_relationship}
                    maxLength={500}
                    rows={3}
                    onChange={event => replaceScene({ host_relationship: event.target.value })}
                  />
                  <FieldError path="scene.host_relationship" errors={errors} />
                </div>
                <div className="flex flex-col gap-element">
                  <Label htmlFor="audience-relationship">角色如何看待聊天室觀眾</Label>
                  <Textarea
                    id="audience-relationship"
                    value={draft.scene.audience_relationship}
                    maxLength={500}
                    rows={3}
                    onChange={event => replaceScene({ audience_relationship: event.target.value })}
                  />
                  <FieldError path="scene.audience_relationship" errors={errors} />
                </div>
              </div>
              {draft.scene.channel_stage !== 'chat_adapted' && (
                <div className="flex flex-col gap-element">
                  <Label htmlFor="host-mapping">實況主在故事中的身分（選填）</Label>
                  <Input
                    id="host-mapping"
                    value={draft.scene.host_character_mapping ?? ''}
                    onChange={event =>
                      replaceScene({ host_character_mapping: event.target.value || null })
                    }
                  />
                </div>
              )}
              {draft.scene.channel_stage !== 'in_world_visitors' && (
                <div className="flex flex-col gap-element">
                  <Label htmlFor="adaptation-note">兩個世界如何相接</Label>
                  <Textarea
                    id="adaptation-note"
                    value={draft.scene.adaptation_note}
                    maxLength={800}
                    rows={3}
                    onChange={event => replaceScene({ adaptation_note: event.target.value })}
                  />
                  <FieldError path="scene.adaptation_note" errors={errors} />
                </div>
              )}
            </>
          )}

          {step === 5 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                背景條目是角色可在相關話題中參考的補充設定。每條只寫一個人物、地點、組織或事件。
              </p>
              <div className="flex flex-col gap-element">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <Label>背景條目</Label>
                    <p className="mt-1 text-label text-muted-foreground">
                      每條聚焦一個人物、地點、組織或事件。
                    </p>
                  </div>
                  {draft.lore_entries.length < 30 && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        setDraft(current => ({
                          ...current,
                          lore_entries: [
                            ...current.lore_entries,
                            {
                              subject: '',
                              aliases: [],
                              content: '',
                              known_at_stage: true,
                              contains_spoilers: false,
                              priority: 50,
                            },
                          ],
                        }))
                      }
                    >
                      新增背景
                    </Button>
                  )}
                </div>
                {draft.lore_entries.map((entry, index) => (
                  <div key={index} className="grid gap-3 rounded-md bg-muted/50 p-3 sm:grid-cols-2">
                    <Input
                      aria-label={`背景主題 ${index + 1}`}
                      value={entry.subject}
                      placeholder="主題名稱"
                      onChange={event => updateLore(index, { subject: event.target.value })}
                    />
                    <Input
                      aria-label={`背景別名 ${index + 1}`}
                      value={entry.aliases.join('、')}
                      placeholder="其他稱呼，以逗號分隔"
                      onChange={event =>
                        updateLore(index, { aliases: splitAliases(event.target.value) })
                      }
                    />
                    <Textarea
                      aria-label={`背景內容 ${index + 1}`}
                      className="sm:col-span-2"
                      value={entry.content}
                      maxLength={800}
                      rows={3}
                      placeholder="角色可以知道並回答的內容"
                      onChange={event => updateLore(index, { content: event.target.value })}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-3 sm:col-span-2">
                      <label className="flex items-center gap-2 text-sub">
                        <Switch
                          checked={entry.known_at_stage}
                          onCheckedChange={known_at_stage => updateLore(index, { known_at_stage })}
                        />
                        角色此時已知道
                      </label>
                      <label className="flex items-center gap-2 text-sub">
                        <Switch
                          checked={entry.contains_spoilers}
                          onCheckedChange={contains_spoilers =>
                            updateLore(index, { contains_spoilers })
                          }
                        />
                        包含作品範圍外的劇情
                      </label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setDraft(current => ({
                            ...current,
                            lore_entries: current.lore_entries.filter(
                              (_, itemIndex) => itemIndex !== index
                            ),
                          }))
                        }
                      >
                        移除此條
                      </Button>
                    </div>
                    <details className="sm:col-span-2">
                      <summary className="cursor-pointer text-label text-muted-foreground">
                        進階：重要程度
                      </summary>
                      <div className="mt-2 flex items-center gap-3">
                        <Input
                          aria-label={`背景重要程度 ${index + 1}`}
                          type="number"
                          min={0}
                          max={100}
                          value={entry.priority}
                          className="w-24"
                          onChange={event =>
                            updateLore(index, {
                              priority: Math.max(0, Math.min(100, Number(event.target.value))),
                            })
                          }
                        />
                        <span className="text-label text-muted-foreground">
                          多條內容同時相關時，數值較高的會先參考。
                        </span>
                      </div>
                    </details>
                  </div>
                ))}
              </div>
              <Separator />
              <StringListEditor
                label="說話示例"
                description="最多三句不同情境的原創示例；只參考語氣，不會照抄成固定台詞。"
                values={draft.example_replies}
                maxItems={3}
                maxLength={120}
                addLabel="新增示例"
                onChange={example_replies => setDraft(current => ({ ...current, example_replies }))}
              />
            </>
          )}

          {step === 6 && (
            <>
              <p className="max-w-prose text-sub text-muted-foreground">
                先確認以下內容是否符合你想演出的角色。這一步只整理你填過的內容，不會呼叫模型或消耗免費額度。
              </p>
              <dl className="divide-y rounded-md border px-4">
                {reviewRows.map(([label, value]) => (
                  <div key={label} className="grid gap-1 py-3 sm:grid-cols-[8rem_1fr]">
                    <dt className="text-label font-medium text-muted-foreground">{label}</dt>
                    <dd className="text-sub whitespace-pre-wrap">{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ['一般提問', '會先用角色的說話方式直接回答。'],
                  ['人物關係', '問到相關人物時，才會參考對應的關係與背景。'],
                  ['未知與後續劇情', '角色不知道或不在作品範圍內的事，不會當作已知內容回答。'],
                  ['要求跳出設定', '觀眾要求忽略角色設定或安全規則時，仍會維持原本界線。'],
                ].map(([title, description]) => (
                  <div key={title} className="rounded-md bg-muted/50 p-3">
                    <p className="text-sub font-medium">{title}</p>
                    <p className="mt-1 text-label text-muted-foreground">{description}</p>
                  </div>
                ))}
              </div>
              {Object.keys(errors).length > 0 && (
                <div
                  className="rounded-md border border-destructive/50 bg-destructive/5 p-3"
                  role="alert"
                >
                  <p className="text-sub font-medium text-destructive">請補寫以下內容</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-label text-destructive">
                    {Object.values(errors).map((message, index) => (
                      <li key={`${message}-${index}`}>{message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </CardContent>
      </div>
      <CardFooter className="justify-between border-t">
        <Button
          type="button"
          variant="ghost"
          onClick={() => (step === 0 ? requestCancel() : setStep(current => current - 1))}
          disabled={saving}
        >
          {step === 0 ? '取消' : '上一步'}
        </Button>
        {step < STEPS.length - 1 ? (
          <Button type="button" onClick={handleContinue} disabled={saving}>
            {saving && <Spinner className="mr-1.5 h-3 w-3" />}
            儲存並繼續
          </Button>
        ) : (
          <Button type="button" onClick={handleFinish} disabled={saving}>
            {saving && <Spinner className="mr-1.5 h-3 w-3" />}
            {canRetryActivation ? '再次嘗試使用' : '完成並使用'}
          </Button>
        )}
      </CardFooter>
    </Card>
  )

  function updateLore(index: number, patch: Partial<RoleplayLoreEntry>) {
    setDraft(current => {
      const lore_entries = [...current.lore_entries]
      lore_entries[index] = { ...lore_entries[index], ...patch }
      return { ...current, lore_entries }
    })
  }
}
