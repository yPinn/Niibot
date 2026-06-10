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
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import { Icon, SlideUp, Spinner } from '@/components/primitives'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Skeleton,
  Switch,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import {
  COMMAND_INFO,
  LANG_OPTIONS,
  PERSONA_PRESETS,
  PROVIDERS,
  REFUSAL_OPTIONS,
  ROLE_OPTIONS,
} from './ai/constants'
import { EmoteSection, OptionGroup } from './ai/EmoteSection'
import { longestCommonPrefix } from './ai/utils'

export default function AIModule() {
  useDocumentTitle('AI Assistant')

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
          catchphrase: s.catchphrase ?? '',
          enabled_emotes: s.enabled_emotes ?? [],
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
    draft.catchphrase !== saved.catchphrase ||
    draft.response_lang !== saved.response_lang ||
    draft.refusal_style !== saved.refusal_style

  const isCmdDirty = draft.cooldown !== saved.cooldown || draft.min_role !== saved.min_role

  const isDefault =
    draft.bot_name === AI_SETTINGS_DEFAULT.bot_name &&
    draft.persona === AI_SETTINGS_DEFAULT.persona &&
    draft.self_pronoun === AI_SETTINGS_DEFAULT.self_pronoun &&
    draft.catchphrase === AI_SETTINGS_DEFAULT.catchphrase &&
    draft.response_lang === AI_SETTINGS_DEFAULT.response_lang &&
    draft.refusal_style === AI_SETTINGS_DEFAULT.refusal_style

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
        catchphrase: draft.catchphrase,
        response_lang: draft.response_lang,
        refusal_style: draft.refusal_style,
      })
      const normalized = { ...updated, enabled_emotes: updated.enabled_emotes ?? [] }
      setSaved(normalized)
      setDraft(prev => ({ ...normalized, cooldown: prev.cooldown, min_role: prev.min_role }))
      toast.success('角色設定已儲存')
    } catch {
      toast.error('儲存失敗，請重試')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    setSaving(true)
    try {
      const updated = await resetAISettings()
      const normalized = { ...updated, enabled_emotes: updated.enabled_emotes ?? [] }
      setSaved(normalized)
      setDraft(normalized)
      toast.success('已重設為預設值')
    } catch {
      toast.error('重設失敗，請重試')
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
      const normalized = { ...updated, enabled_emotes: updated.enabled_emotes ?? [] }
      setSaved(normalized)
      setDraft(prev => ({
        ...normalized,
        bot_name: prev.bot_name,
        persona: prev.persona,
        self_pronoun: prev.self_pronoun,
        catchphrase: prev.catchphrase,
        response_lang: prev.response_lang,
        refusal_style: prev.refusal_style,
      }))
      toast.success('指令設定已儲存')
    } catch {
      toast.error('儲存失敗，請重試')
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
    } catch {
      setSaved(s => ({ ...s, enabled: prev }))
      setDraft(d => ({ ...d, enabled: prev }))
      toast.error('切換失敗，請重試')
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
        {/* Left — all editable cards */}
        <SlideUp inView className="flex flex-col gap-section">
          {/* Identity */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>角色</CardTitle>
                <Button size="sm" onClick={handleSave} disabled={!isDirty || disabled}>
                  {saving ? (
                    <Spinner className="mr-1.5 h-3 w-3" />
                  ) : (
                    <Icon icon="fa-solid fa-floppy-disk" className="mr-1.5 text-label" />
                  )}
                  儲存
                </Button>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* Presets */}
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>懶人包</Label>
                  <p className="text-label text-muted-foreground">
                    快速套用預設人設，套用後仍可自行調整
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

              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label htmlFor="bot-name">Bot 名稱</Label>
                  <p className="text-label text-muted-foreground">聊天室裡叫我什麼名字？</p>
                </div>
                <Input
                  id="bot-name"
                  value={draft.bot_name}
                  onChange={e => patch('bot_name', e.target.value)}
                  maxLength={50}
                  placeholder="Niibot"
                  disabled={disabled}
                  className="max-w-sm"
                />
              </div>

              {/* Self pronoun + catchphrase side by side */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-section">
                <div className="flex flex-col gap-element">
                  <div className="flex flex-col gap-0.5">
                    <Label htmlFor="self-pronoun">自稱</Label>
                    <p className="text-label text-muted-foreground">說話時稱呼自己</p>
                  </div>
                  <Input
                    id="self-pronoun"
                    value={draft.self_pronoun}
                    onChange={e => patch('self_pronoun', e.target.value)}
                    maxLength={20}
                    placeholder="我"
                    disabled={disabled}
                  />
                </div>
                <div className="flex flex-col gap-element">
                  <div className="flex flex-col gap-0.5">
                    <Label htmlFor="catchphrase">口頭禪</Label>
                    <p className="text-label text-muted-foreground">句尾習慣用語（留空則不加）</p>
                  </div>
                  <Input
                    id="catchphrase"
                    value={draft.catchphrase}
                    onChange={e => patch('catchphrase', e.target.value)}
                    maxLength={50}
                    placeholder="懂嗎、喔！…"
                    disabled={disabled}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-element">
                <div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="persona">個性描述</Label>
                    <span className="font-mono text-label text-muted-foreground">
                      {(draft.persona ?? '').length} / 300
                    </span>
                  </div>
                  <p className="mt-0.5 text-label text-muted-foreground">
                    把我設定成什麼樣的角色？描述越詳細，我就越能扮好
                  </p>
                </div>
                <textarea
                  id="persona"
                  value={draft.persona ?? ''}
                  onChange={e => patch('persona', e.target.value)}
                  maxLength={300}
                  rows={4}
                  placeholder="幽默風趣、愛開玩笑…（留空代表無特別個性）"
                  disabled={disabled}
                  className="w-full rounded-md border border-input bg-transparent dark:bg-input/30 px-3 py-2 leading-relaxed resize-none shadow-xs focus:outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              {(isDirty || !isDefault) && (
                <div className="flex justify-end gap-2 border-t pt-section">
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
                          catchphrase: saved.catchphrase,
                          response_lang: saved.response_lang,
                          refusal_style: saved.refusal_style,
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
                </div>
              )}
            </CardContent>
          </Card>

          {/* Language + Refusal */}
          <Card>
            <CardHeader>
              <CardTitle>說話方式</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>語言</Label>
                  <p className="text-label text-muted-foreground">
                    用什麼語言跟大家聊？「自動」會跟著觀眾的語言切換
                  </p>
                </div>
                <OptionGroup
                  options={LANG_OPTIONS}
                  value={draft.response_lang}
                  onChange={v => patch('response_lang', v)}
                  disabled={disabled}
                />
              </div>
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>拒絕風格</Label>
                  <p className="text-label text-muted-foreground">
                    遇到答不了的問題，用什麼方式應付觀眾？
                  </p>
                </div>
                <OptionGroup
                  options={REFUSAL_OPTIONS}
                  value={draft.refusal_style}
                  onChange={v => patch('refusal_style', v)}
                  disabled={disabled}
                />
              </div>
            </CardContent>
          </Card>
        </SlideUp>

        {/* Right — reference info + emotes */}
        <SlideUp inView delay={0.05} className="flex flex-col gap-section">
          {/* Command info + current model */}
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle>指令設定</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
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
                </div>
              </div>
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
                    {PROVIDERS[0].model}
                  </span>
                </div>
              </div>
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label htmlFor="cooldown">冷卻時間</Label>
                  <p className="text-label text-muted-foreground">兩次觸發之間的最短間隔（秒）</p>
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    id="cooldown"
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
                    className="w-24"
                  />
                  <span className="text-sub text-muted-foreground">秒</span>
                </div>
              </div>
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>最低身份</Label>
                  <p className="text-label text-muted-foreground">哪些觀眾可以使用此指令？</p>
                </div>
                <OptionGroup
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
              <div className="flex items-center gap-2">
                <CardTitle className="shrink-0">我的貼圖</CardTitle>
                <Input
                  placeholder="搜尋貼圖…"
                  value={emoteSearch}
                  onChange={e => setEmoteSearch(e.target.value)}
                  className="ml-auto h-7 text-label w-32 shrink-0"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sub text-muted-foreground">
                  顯示 Bot 可使用的頻道及全球貼圖；半透明表示 Bot
                  目前無使用權限，右上角徽章標示限制類型
                </span>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-element">
              {emotesLoading ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] gap-1">
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
