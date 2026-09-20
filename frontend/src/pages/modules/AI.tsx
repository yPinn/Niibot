import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  AI_SETTINGS_DEFAULT,
  type AISettings,
  getTenantAISettings,
  patchTenantAISettings,
  resetTenantAISettings,
} from '@/api/aiSettings'
import { type ChannelBadges, getChannelBadges } from '@/api/analytics'
import { type EmoteItem, getTenantChannelEmotes } from '@/api/emotes'
import { usePersonaMode as switchToPersonaMode } from '@/api/roleplay'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import {
  Button,
  Card,
  CardContent,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useTenant } from '@/contexts/TenantContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import { PersonaPanel } from './ai/PersonaPanel'
import { RoleplayWorkspace } from './ai/RoleplayWorkspace'

function normalizeSettings(settings: AISettings): AISettings {
  return {
    ...AI_SETTINGS_DEFAULT,
    ...settings,
    persona: settings.persona ?? '',
    self_pronoun: settings.self_pronoun ?? '我',
    audience_reference: settings.audience_reference ?? '大家',
    tone_preset: settings.tone_preset ?? 'neutral',
    catchphrase: settings.catchphrase ?? '',
    catchphrase_frequency: settings.catchphrase_frequency ?? 'off',
    example_replies: settings.example_replies ?? [],
    enabled_emotes: settings.enabled_emotes ?? [],
    memory_enabled: settings.memory_enabled ?? false,
  }
}

interface AIWorkspaceProps {
  channelId: string
  tenantRole: string
  twitchModel: string | null | undefined
}

function AIWorkspace({ channelId, tenantRole, twitchModel }: AIWorkspaceProps) {
  const [editorTab, setEditorTab] = useState<'persona' | 'roleplay'>('persona')

  const [saved, setSaved] = useState<AISettings>(AI_SETTINGS_DEFAULT)
  const [draft, setDraft] = useState<AISettings>(AI_SETTINGS_DEFAULT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settingsError, setSettingsError] = useState(false)
  const [reloadNonce, setReloadNonce] = useState(0)

  const [emotes, setEmotes] = useState<EmoteItem[]>([])
  const [emotesLoading, setEmotesLoading] = useState(true)
  const [channelBadges, setChannelBadges] = useState<ChannelBadges | null>(null)

  useEffect(() => {
    let active = true

    getTenantAISettings(channelId)
      .then(settings => {
        if (!active) return
        const normalized = normalizeSettings(settings)
        setSaved(normalized)
        setDraft(normalized)
      })
      .catch(() => {
        if (!active) return
        setSettingsError(true)
        toast.error('載入設定失敗')
      })
      .finally(() => active && setLoading(false))

    getTenantChannelEmotes(channelId)
      .then(response => active && setEmotes(response.emotes))
      .catch(() => active && toast.error('貼圖載入失敗'))
      .finally(() => active && setEmotesLoading(false))

    if (tenantRole === 'owner') {
      getChannelBadges()
        .then(value => active && setChannelBadges(value))
        .catch(() => {})
    }

    return () => {
      active = false
    }
  }, [channelId, reloadNonce, tenantRole])

  const patch = <K extends keyof AISettings>(key: K, value: AISettings[K]) =>
    setDraft(previous => ({ ...previous, [key]: value }))

  async function handleSave() {
    if (!channelId) return
    if (!draft.bot_name.trim()) {
      toast.error('Bot 名稱不能為空')
      return
    }
    setSaving(true)
    try {
      const updated = normalizeSettings(
        await patchTenantAISettings(channelId, {
          bot_name: draft.bot_name,
          persona: draft.persona,
          self_pronoun: draft.self_pronoun,
          tone_preset: draft.tone_preset,
          catchphrase: draft.catchphrase,
          catchphrase_frequency: draft.catchphrase_frequency,
          example_replies: draft.example_replies.map(reply => reply.trim()).filter(Boolean),
          response_lang: draft.response_lang,
          refusal_style: draft.refusal_style,
          memory_enabled: draft.memory_enabled,
        })
      )
      setSaved(updated)
      setDraft(previous => ({
        ...updated,
        cooldown: previous.cooldown,
        min_role: previous.min_role,
      }))
      toast.success('角色設定已儲存')
    } catch (error) {
      toastApiError(error, '儲存失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    if (!channelId) return
    setSaving(true)
    try {
      const updated = normalizeSettings(await resetTenantAISettings(channelId))
      setSaved(updated)
      setDraft(updated)
      toast.success('已重設為預設值')
    } catch (error) {
      toastApiError(error, '重設失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleCommandSave() {
    if (!channelId) return
    setSaving(true)
    try {
      const updated = normalizeSettings(
        await patchTenantAISettings(channelId, {
          cooldown: draft.cooldown,
          min_role: draft.min_role,
        })
      )
      setSaved(updated)
      setDraft(previous => ({
        ...updated,
        bot_name: previous.bot_name,
        persona: previous.persona,
        self_pronoun: previous.self_pronoun,
        audience_reference: previous.audience_reference,
        tone_preset: previous.tone_preset,
        catchphrase: previous.catchphrase,
        catchphrase_frequency: previous.catchphrase_frequency,
        example_replies: previous.example_replies,
        response_lang: previous.response_lang,
        refusal_style: previous.refusal_style,
        memory_enabled: previous.memory_enabled,
      }))
      toast.success('指令設定已儲存')
    } catch (error) {
      toastApiError(error, '儲存失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleEnabled(value: boolean) {
    if (!channelId) return
    const previous = saved.enabled
    setSaved(settings => ({ ...settings, enabled: value }))
    setDraft(settings => ({ ...settings, enabled: value }))
    try {
      await patchTenantAISettings(channelId, { enabled: value })
      toast.success(value ? 'AI 助手已啟用' : 'AI 助手已停用')
    } catch (error) {
      setSaved(settings => ({ ...settings, enabled: previous }))
      setDraft(settings => ({ ...settings, enabled: previous }))
      toastApiError(error, '切換失敗，請重試')
    }
  }

  async function handleUsePersona() {
    if (!channelId || saved.assistant_mode === 'persona') return
    setSaving(true)
    try {
      const mode = await switchToPersonaMode(channelId)
      setSaved(current => ({ ...current, ...mode }))
      setDraft(current => ({ ...current, ...mode }))
      toast.success('已改用說話風格')
    } catch (error) {
      toastApiError(error, '切換說話風格失敗')
    } finally {
      setSaving(false)
    }
  }

  function handleModeChange(
    assistant_mode: 'persona' | 'roleplay',
    active_roleplay_revision_id: number | null
  ) {
    setSaved(current => ({ ...current, assistant_mode, active_roleplay_revision_id }))
    setDraft(current => ({ ...current, assistant_mode, active_roleplay_revision_id }))
  }

  return settingsError ? (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-empty text-center">
        <div>
          <p className="text-sub font-medium">無法載入 AI 設定</p>
          <p className="mt-1 text-label text-muted-foreground">
            目前沒有顯示或套用預設值，請確認連線後重新載入。
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            setSettingsError(false)
            setLoading(true)
            setEmotesLoading(true)
            setReloadNonce(value => value + 1)
          }}
        >
          重新載入
        </Button>
      </CardContent>
    </Card>
  ) : (
    <Tabs
      value={editorTab}
      onValueChange={value => setEditorTab(value as 'persona' | 'roleplay')}
      className="flex flex-col gap-section"
    >
      <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sub font-medium">
            {loading
              ? '正在載入 AI 設定'
              : saved.assistant_mode === 'roleplay'
                ? '故事角色使用中'
                : '說話風格使用中'}
          </p>
          <p className="mt-1 text-label text-muted-foreground">
            {loading
              ? '正在讀取目前工作區的設定。'
              : `${saved.enabled ? 'AI 回覆已啟用' : 'AI 回覆目前已停用'}；切換下方頁籤只會改變編輯畫面。`}
          </p>
        </div>
        <TabsList aria-label="AI 設定類型">
          <TabsTrigger value="persona" disabled={loading}>
            說話風格
          </TabsTrigger>
          <TabsTrigger value="roleplay" disabled={loading}>
            故事角色
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="persona">
        <PersonaPanel
          saved={saved}
          draft={draft}
          setDraft={setDraft}
          patch={patch}
          loading={loading}
          saving={saving}
          twitchModel={twitchModel}
          emotes={emotes}
          emotesLoading={emotesLoading}
          channelBadges={channelBadges}
          onSave={handleSave}
          onReset={handleReset}
          onCommandSave={handleCommandSave}
          onToggleEnabled={handleToggleEnabled}
          onUsePersona={handleUsePersona}
        />
      </TabsContent>

      <TabsContent value="roleplay">
        <RoleplayWorkspace
          key={channelId}
          channelId={channelId}
          assistantMode={saved.assistant_mode}
          activeRevisionId={saved.active_roleplay_revision_id}
          onModeChange={handleModeChange}
        />
      </TabsContent>
    </Tabs>
  )
}

export default function AIModule() {
  useDocumentTitle('AI Assistant')
  const { twitch } = useServiceStatus()
  const { activeTenant } = useTenant()

  return (
    <PageMain>
      <PageHeader
        title="AI Assistant"
        description="設定 AI 在聊天室的說話方式，或讓它演繹一位有故事背景的角色"
      />
      {activeTenant ? (
        <AIWorkspace
          key={activeTenant.channel_id}
          channelId={activeTenant.channel_id}
          tenantRole={activeTenant.role}
          twitchModel={twitch.ai_model}
        />
      ) : (
        <Card>
          <CardContent className="py-empty text-center text-sub text-muted-foreground">
            目前沒有可管理的頻道工作區。
          </CardContent>
        </Card>
      )}
    </PageMain>
  )
}
