import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  AI_SETTINGS_DEFAULT,
  type AISettings,
  type EmoteItem,
  getAIEmotes,
  getAISettings,
  patchAISettings,
  resetAISettings,
} from '@/api/aiSettings'
import { type ChannelBadges, getChannelBadges } from '@/api/analytics'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, OptionPicker, SlideUp, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Separator,
  Skeleton,
  Switch,
  Textarea,
} from '@/components/ui'
import { useServiceStatus } from '@/contexts/ServiceStatusContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import {
  CATCHPHRASE_FREQUENCY_OPTIONS,
  COMMAND_INFO,
  LANG_OPTIONS,
  PERSONA_PRESETS,
  REFUSAL_OPTIONS,
  ROLE_OPTIONS,
  TONE_OPTIONS,
} from './ai/constants'
import { EmoteSection } from './ai/EmoteSection'
import { longestCommonPrefix } from './ai/utils'

export default function AIModule() {
  useDocumentTitle('AI Assistant')
  const { twitch } = useServiceStatus()

  const [saved, setSaved] = useState<AISettings>(AI_SETTINGS_DEFAULT)
  const [draft, setDraft] = useState<AISettings>(AI_SETTINGS_DEFAULT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [emotes, setEmotes] = useState<EmoteItem[]>([])
  const [emotesLoading, setEmotesLoading] = useState(true)
  const [emoteSearch, setEmoteSearch] = useState('')

  const [channelBadges, setChannelBadges] = useState<ChannelBadges | null>(null)

  useEffect(() => {
    getAISettings()
      .then(s => {
        const normalized: AISettings = {
          ...AI_SETTINGS_DEFAULT,
          ...s,
          persona: s.persona ?? '',
          self_pronoun: s.self_pronoun ?? '我',
          audience_reference: s.audience_reference ?? '大家',
          tone_preset: s.tone_preset ?? 'neutral',
          catchphrase: s.catchphrase ?? '',
          catchphrase_frequency: s.catchphrase_frequency ?? 'off',
          example_replies: s.example_replies ?? [],
          enabled_emotes: s.enabled_emotes ?? [],
          memory_enabled: s.memory_enabled ?? false,
        }
        setSaved(normalized)
        setDraft(normalized)
      })
      .catch(() => toast.error('載入設定失敗'))
      .finally(() => setLoading(false))

    getAIEmotes()
      .then(setEmotes)
      .catch(() => toast.error('貼圖載入失敗'))
      .finally(() => setEmotesLoading(false))

    getChannelBadges()
      .then(setChannelBadges)
      .catch(() => {})
  }, [])

  const patch = <K extends keyof AISettings>(key: K, value: AISettings[K]) =>
    setDraft(prev => ({ ...prev, [key]: value }))

  const isDirty =
    draft.bot_name !== saved.bot_name ||
    draft.persona !== saved.persona ||
    draft.self_pronoun !== saved.self_pronoun ||
    draft.tone_preset !== saved.tone_preset ||
    draft.catchphrase !== saved.catchphrase ||
    draft.catchphrase_frequency !== saved.catchphrase_frequency ||
    JSON.stringify(draft.example_replies) !== JSON.stringify(saved.example_replies) ||
    draft.response_lang !== saved.response_lang ||
    draft.refusal_style !== saved.refusal_style ||
    draft.memory_enabled !== saved.memory_enabled

  const isCmdDirty = draft.cooldown !== saved.cooldown || draft.min_role !== saved.min_role

  const isDefault =
    draft.bot_name === AI_SETTINGS_DEFAULT.bot_name &&
    draft.persona === AI_SETTINGS_DEFAULT.persona &&
    draft.self_pronoun === AI_SETTINGS_DEFAULT.self_pronoun &&
    draft.tone_preset === AI_SETTINGS_DEFAULT.tone_preset &&
    draft.catchphrase === AI_SETTINGS_DEFAULT.catchphrase &&
    draft.catchphrase_frequency === AI_SETTINGS_DEFAULT.catchphrase_frequency &&
    draft.example_replies.length === 0 &&
    draft.response_lang === AI_SETTINGS_DEFAULT.response_lang &&
    draft.refusal_style === AI_SETTINGS_DEFAULT.refusal_style &&
    draft.memory_enabled === AI_SETTINGS_DEFAULT.memory_enabled

  const channelPrefix = useMemo(
    () => longestCommonPrefix(emotes.filter(e => e.emote_type !== 'globals').map(e => e.name)),
    [emotes]
  )

  const { followerEmotes, subscriptionEmotes, bitsEmotes, globalEmotes } = useMemo(() => {
    const q = emoteSearch.trim().toLowerCase()
    const match = (e: EmoteItem) => !q || e.name.toLowerCase().includes(q)
    const animFirst = (a: EmoteItem, b: EmoteItem) =>
      a.animated === b.animated ? 0 : a.animated ? 1 : -1
    const byName = (arr: EmoteItem[]) =>
      [...arr].sort((a, b) => animFirst(a, b) || a.name.localeCompare(b.name))
    const bySub = (arr: EmoteItem[]) =>
      [...arr].sort((a, b) => {
        const anim = animFirst(a, b)
        if (anim !== 0) return anim
        const t = (parseInt(a.tier) || 0) - (parseInt(b.tier) || 0)
        return t !== 0 ? t : a.name.localeCompare(b.name)
      })
    return {
      followerEmotes: byName(emotes.filter(e => e.emote_type === 'follower' && match(e))),
      subscriptionEmotes: bySub(emotes.filter(e => e.emote_type === 'subscriptions' && match(e))),
      bitsEmotes: byName(emotes.filter(e => e.emote_type === 'bitstier' && match(e))),
      globalEmotes: byName(emotes.filter(e => e.emote_type === 'globals' && match(e))),
    }
  }, [emotes, emoteSearch])

  async function handleSave() {
    if (!draft.bot_name.trim()) {
      toast.error('Bot 名稱不能為空')
      return
    }
    setSaving(true)
    try {
      const updated = await patchAISettings({
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
      const normalized = {
        ...updated,
        example_replies: updated.example_replies ?? [],
        enabled_emotes: updated.enabled_emotes ?? [],
      }
      setSaved(normalized)
      setDraft(prev => ({ ...normalized, cooldown: prev.cooldown, min_role: prev.min_role }))
      toast.success('角色設定已儲存')
    } catch (e) {
      toastApiError(e, '儲存失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    setSaving(true)
    try {
      const updated = await resetAISettings()
      const normalized = {
        ...updated,
        example_replies: updated.example_replies ?? [],
        enabled_emotes: updated.enabled_emotes ?? [],
      }
      setSaved(normalized)
      setDraft(normalized)
      toast.success('已重設為預設值')
    } catch (e) {
      toastApiError(e, '重設失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleCmdSave() {
    setSaving(true)
    try {
      const updated = await patchAISettings({
        cooldown: draft.cooldown,
        min_role: draft.min_role,
      })
      const normalized = {
        ...updated,
        example_replies: updated.example_replies ?? [],
        enabled_emotes: updated.enabled_emotes ?? [],
      }
      setSaved(normalized)
      setDraft(prev => ({
        ...normalized,
        bot_name: prev.bot_name,
        persona: prev.persona,
        self_pronoun: prev.self_pronoun,
        audience_reference: prev.audience_reference,
        tone_preset: prev.tone_preset,
        catchphrase: prev.catchphrase,
        catchphrase_frequency: prev.catchphrase_frequency,
        example_replies: prev.example_replies,
        response_lang: prev.response_lang,
        refusal_style: prev.refusal_style,
        memory_enabled: prev.memory_enabled,
      }))
      toast.success('指令設定已儲存')
    } catch (e) {
      toastApiError(e, '儲存失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggleEnabled(value: boolean) {
    const prev = saved.enabled
    setSaved(s => ({ ...s, enabled: value }))
    setDraft(d => ({ ...d, enabled: value }))
    try {
      await patchAISettings({ enabled: value })
      toast.success(value ? 'AI 助手已啟用' : 'AI 助手已停用')
    } catch (e) {
      setSaved(s => ({ ...s, enabled: prev }))
      setDraft(d => ({ ...d, enabled: prev }))
      toastApiError(e, '切換失敗，請重試')
    }
  }

  const disabled = loading || saving
  const totalEmotes =
    followerEmotes.length + subscriptionEmotes.length + bitsEmotes.length + globalEmotes.length

  return (
    <PageMain>
      <PageHeader
        title="AI Assistant"
        description="叫我什麼、怎麼說話、遇到奇怪問題怎麼辦 — 都在這裡設定"
      />

      {/* 2:1 — editable left | reference right */}
      <div className="grid gap-section lg:grid-cols-[2fr_1fr] items-start">
        {/* Left — identity + speaking style, one form / one save state */}
        <SlideUp inView className="flex flex-col gap-section">
          <Card>
            <CardHeader>
              <CardTitle>角色設定</CardTitle>
              <CardAction>
                <Button size="sm" onClick={handleSave} disabled={!isDirty || disabled}>
                  {saving ? (
                    <Spinner className="mr-1.5 h-3 w-3" />
                  ) : (
                    <Icon icon="fa-solid fa-floppy-disk" className="mr-1.5 text-label" />
                  )}
                  儲存
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* Presets */}
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>角色範本</Label>
                  <p className="text-label text-muted-foreground">
                    套用後仍可微調下方欄位；不會改變婉拒方式。
                  </p>
                </div>
                <div className="flex gap-2 overflow-x-auto pb-0.5">
                  {PERSONA_PRESETS.map(preset => (
                    <button
                      key={preset.name}
                      type="button"
                      disabled={disabled}
                      onClick={() => setDraft(prev => ({ ...prev, ...preset.values }))}
                      className="select-none flex shrink-0 flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left transition-colors hover:bg-accent disabled:opacity-50 min-w-24"
                    >
                      <span className="flex items-center gap-1.5 text-sub font-medium">
                        <Icon
                          icon={preset.icon}
                          size="sm"
                          wrapperClassName="text-muted-foreground"
                        />
                        {preset.name}
                      </span>
                      <span className="text-label text-muted-foreground">{preset.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Identity — same field family, same grid so widths stay consistent */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-section">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="bot-name">Bot 名稱</Label>
                  <Input
                    id="bot-name"
                    value={draft.bot_name}
                    onChange={e => patch('bot_name', e.target.value)}
                    maxLength={50}
                    placeholder="Niibot"
                    disabled={disabled}
                  />
                </div>
                <div className="flex flex-col gap-element">
                  <Label htmlFor="self-pronoun">自稱</Label>
                  <Input
                    id="self-pronoun"
                    value={draft.self_pronoun}
                    onChange={e => patch('self_pronoun', e.target.value)}
                    maxLength={20}
                    placeholder="我"
                    disabled={disabled}
                  />
                </div>
              </div>
              <p className="text-label text-muted-foreground">
                自稱只在句意需要時使用，不會要求每則回覆固定出現。
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-[1fr_1.35fr] gap-section">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="catchphrase">口頭禪</Label>
                  <Input
                    id="catchphrase"
                    value={draft.catchphrase}
                    onChange={e => patch('catchphrase', e.target.value)}
                    maxLength={50}
                    placeholder="懂嗎、喔！…（留空則不加）"
                    disabled={disabled}
                  />
                </div>
                <div className="flex flex-col gap-element">
                  <Label>口頭禪頻率</Label>
                  <OptionPicker
                    options={CATCHPHRASE_FREQUENCY_OPTIONS}
                    value={draft.catchphrase_frequency}
                    onChange={v => patch('catchphrase_frequency', v)}
                    disabled={disabled || !draft.catchphrase.trim()}
                  />
                  <p className="text-label text-muted-foreground">
                    這是使用傾向，不是精準比例；需要自然回覆時建議選「不使用」。
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-element">
                <div className="flex items-center justify-between">
                  <Label htmlFor="persona">個性描述</Label>
                  <span className="font-mono text-label text-muted-foreground">
                    {(draft.persona ?? '').length} / 300
                  </span>
                </div>
                <p className="text-label text-muted-foreground">
                  先把答案說清楚，再自然帶入角色；避免要求每句都表演。
                </p>
                <Textarea
                  id="persona"
                  value={draft.persona ?? ''}
                  onChange={e => patch('persona', e.target.value)}
                  maxLength={300}
                  rows={3}
                  placeholder="例如：反應俐落，先回答；情境輕鬆時偶爾善意吐槽"
                  disabled={disabled}
                  className="resize-none leading-relaxed"
                />
              </div>

              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>示例回覆</Label>
                  <p className="text-label text-muted-foreground">
                    最多三句不同情境的理想回答；模型只參考語氣與節奏，不會把示例當成固定台詞
                  </p>
                </div>
                <div className="grid gap-2">
                  {[0, 1, 2].map(index => (
                    <Input
                      key={index}
                      aria-label={`示例回覆 ${index + 1}`}
                      value={draft.example_replies[index] ?? ''}
                      onChange={event => {
                        const examples = [...draft.example_replies]
                        examples[index] = event.target.value
                        patch('example_replies', examples)
                      }}
                      maxLength={120}
                      placeholder={`示例 ${index + 1}${index === 0 ? '：簡單來說，重點是這個。' : '（選填）'}`}
                      disabled={disabled}
                    />
                  ))}
                </div>
              </div>

              <Separator />
              <p className="text-sub font-medium">回覆方式</p>

              <div className="flex flex-col gap-element">
                <Label>回覆語氣</Label>
                <OptionPicker
                  options={TONE_OPTIONS}
                  value={draft.tone_preset}
                  onChange={v => patch('tone_preset', v)}
                  disabled={disabled}
                />
              </div>

              <SettingRow title="回覆語言" description="「跟隨提問」會依每次問題使用的語言回答">
                <OptionPicker
                  options={LANG_OPTIONS}
                  value={draft.response_lang}
                  onChange={v => patch('response_lang', v)}
                  disabled={disabled}
                />
              </SettingRow>

              <div className="flex flex-col gap-element">
                <Label>婉拒方式</Label>
                <OptionPicker
                  options={REFUSAL_OPTIONS}
                  value={draft.refusal_style}
                  onChange={v => patch('refusal_style', v)}
                  disabled={disabled}
                />
              </div>

              <SettingRow
                title="短期對話記憶（實驗性）"
                description="只記住同一位觀眾透過 !ai 的最近 2 輪，10 分鐘後失效；不讀一般聊天、不永久保存，服務重啟即清空。"
                className="rounded-md border p-3"
              >
                <Switch
                  aria-label="短期對話記憶（實驗性）"
                  checked={draft.memory_enabled}
                  onCheckedChange={value => patch('memory_enabled', value)}
                  disabled={disabled}
                />
              </SettingRow>
            </CardContent>
            {(isDirty || !isDefault) && (
              <CardFooter className="justify-end gap-2 border-t">
                {isDirty && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setDraft(prev => ({
                        ...prev,
                        bot_name: saved.bot_name,
                        persona: saved.persona,
                        self_pronoun: saved.self_pronoun,
                        tone_preset: saved.tone_preset,
                        catchphrase: saved.catchphrase,
                        catchphrase_frequency: saved.catchphrase_frequency,
                        example_replies: saved.example_replies,
                        response_lang: saved.response_lang,
                        refusal_style: saved.refusal_style,
                        memory_enabled: saved.memory_enabled,
                      }))
                    }
                    disabled={saving}
                  >
                    取消
                  </Button>
                )}
                {!isDefault && (
                  <Button variant="outline" size="sm" onClick={handleReset} disabled={disabled}>
                    {saving ? (
                      <Spinner className="mr-1.5 h-3 w-3" />
                    ) : (
                      <Icon icon="fa-solid fa-rotate-left" className="mr-1.5 text-label" />
                    )}
                    重設預設值
                  </Button>
                )}
              </CardFooter>
            )}
          </Card>
        </SlideUp>

        {/* Right — reference info + emotes */}
        <SlideUp inView delay={0.05} className="flex flex-col gap-section">
          {/* Command info + current model */}
          <Card>
            <CardHeader>
              <CardTitle>指令設定</CardTitle>
              <CardAction className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-label text-muted-foreground">
                  {saved.enabled ? '啟用中' : '已停用'}
                </span>
                <Switch
                  checked={saved.enabled}
                  onCheckedChange={handleToggleEnabled}
                  disabled={loading}
                />
                <div className="h-4 w-px bg-border" />
                {isCmdDirty && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setDraft(prev => ({
                        ...prev,
                        cooldown: saved.cooldown,
                        min_role: saved.min_role,
                      }))
                    }
                    disabled={saving}
                  >
                    取消
                  </Button>
                )}
                <Button size="sm" onClick={handleCmdSave} disabled={!isCmdDirty || disabled}>
                  {saving ? (
                    <Spinner className="mr-1.5 h-3 w-3" />
                  ) : (
                    <Icon icon="fa-solid fa-floppy-disk" className="mr-1.5 text-label" />
                  )}
                  儲存
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              <div className="flex flex-col divide-y">
                {COMMAND_INFO.map(({ label, value }) => (
                  <div key={label} className="flex items-center justify-between py-2.5 first:pt-0">
                    <Label className="text-muted-foreground">{label}</Label>
                    <span className="font-mono text-label">{value}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between py-2.5">
                  <Label className="text-muted-foreground">模型</Label>
                  <span className="font-mono text-label truncate max-w-[55%] text-right">
                    {twitch.ai_model ?? '—'}
                  </span>
                </div>
              </div>
              <SettingRow title="頻道冷卻時間" description="任一觀眾使用後，全頻道需等待的時間。">
                <div className="flex items-center gap-2">
                  <Input
                    aria-label="頻道冷卻時間（秒）"
                    type="number"
                    min={5}
                    max={300}
                    step={5}
                    value={draft.cooldown}
                    onChange={e => {
                      const val = parseInt(e.target.value)
                      if (!isNaN(val)) patch('cooldown', Math.max(5, Math.min(300, val)))
                    }}
                    disabled={disabled}
                    className="w-20"
                  />
                  <span className="text-sub text-muted-foreground">秒</span>
                </div>
              </SettingRow>
              <div className="flex flex-col gap-element">
                <Label>誰可以使用</Label>
                <OptionPicker
                  options={ROLE_OPTIONS}
                  value={draft.min_role}
                  onChange={v => patch('min_role', v)}
                  disabled={disabled}
                />
              </div>
            </CardContent>
          </Card>

          {/* Emote info */}
          <Card>
            <CardHeader>
              <CardTitle>我的貼圖</CardTitle>
              <CardAction>
                <Input
                  placeholder="搜尋貼圖…"
                  value={emoteSearch}
                  onChange={e => setEmoteSearch(e.target.value)}
                  className="h-7 text-label w-32"
                />
              </CardAction>
              <CardDescription>
                顯示 Bot 可使用的頻道及全球貼圖；半透明表示 Bot
                目前無使用權限，右上角徽章標示限制類型
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-element">
              {emotesLoading ? (
                <div className="grid grid-cols-[repeat(auto-fill,5rem)] gap-1">
                  {Array.from({ length: 16 }).map((_, i) => (
                    <div key={i} className="flex flex-col items-center gap-1 p-1.5">
                      <Skeleton className="h-14 w-14 rounded-md" />
                      <Skeleton className="h-3 w-10" />
                    </div>
                  ))}
                </div>
              ) : totalEmotes === 0 ? (
                <p className="py-4 text-center text-label text-muted-foreground">
                  找不到符合的貼圖
                </p>
              ) : (
                <div className="scrollbar flex max-h-96 flex-col gap-3 overflow-y-auto rounded-md border p-3">
                  <EmoteSection
                    label="追隨者"
                    emotes={followerEmotes}
                    prefix={channelPrefix}
                    channelBadges={channelBadges}
                  />
                  <EmoteSection
                    label="訂閱者"
                    emotes={subscriptionEmotes}
                    prefix={channelPrefix}
                    channelBadges={channelBadges}
                  />
                  <EmoteSection
                    label="小奇點"
                    emotes={bitsEmotes}
                    prefix={channelPrefix}
                    channelBadges={channelBadges}
                  />
                  <EmoteSection
                    label="全球貼圖"
                    emotes={globalEmotes}
                    prefix=""
                    channelBadges={channelBadges}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </SlideUp>
      </div>
    </PageMain>
  )
}
