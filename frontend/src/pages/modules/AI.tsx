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
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Label,
  SlideUp,
  Spinner,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TwitchBadge,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ── Constants ────────────────────────────────────────────────────────────────

const LANG_OPTIONS = [
  { value: 'zh-tw' as const, label: '繁中' },
  { value: 'en' as const, label: '英文' },
  { value: 'auto' as const, label: '自動' },
]

const REFUSAL_OPTIONS = [
  { value: 'humorous' as const, label: '冷幽默', desc: '假裝系統錯誤、腦袋當機' },
  { value: 'polite' as const, label: '禮貌拒絕', desc: '直接說無法協助' },
]

const MAX_TOKENS_OPTIONS = [100, 150, 200, 250, 300, 400, 500].map(v => ({
  value: v,
  label: String(v),
}))

const COMMAND_INFO = [
  { label: '指令', value: '!ai / !問' },
  { label: '冷卻時間', value: '15 秒' },
  { label: '用法', value: '!ai <問題>' },
] as const

const PROVIDERS = [
  { name: 'Groq', icon: 'fa-solid fa-bolt', model: 'llama-3.3-70b-versatile', note: '優先' },
  { name: 'Gemini', icon: 'fa-brands fa-google', model: 'gemini-1.5-flash', note: '備援' },
  { name: 'OpenRouter', icon: 'fa-solid fa-route', model: 'free models', note: '最後備援' },
] as const

// ── Helpers ──────────────────────────────────────────────────────────────────

function getBadgeOverlay(
  emote: EmoteItem,
  channelBadges: ChannelBadges | null
): { src: string; label: string } | null {
  if (emote.emote_type === 'subscriptions') {
    return {
      src: channelBadges?.subscriber_1m ?? '/twitch-badges/subscriber/1x.png',
      label: '訂閱限定',
    }
  }
  if (emote.emote_type === 'bitstier') {
    // Twitch API always returns tier="" for bitstier emotes; use first channel bits badge or default
    const channelSrc = channelBadges?.sets?.bits?.[0]?.image_url_1x ?? null
    return {
      src: channelSrc ?? '/twitch-badges/bits/1x.png',
      label: 'Bits 限定',
    }
  }
  return null
}

function longestCommonPrefix(names: string[]): string {
  if (names.length === 0) return ''
  let prefix = names[0]
  for (const name of names) {
    while (!name.startsWith(prefix)) prefix = prefix.slice(0, -1)
    if (!prefix) return ''
  }
  return prefix.length >= 2 ? prefix : ''
}

// ── Sub-components ───────────────────────────────────────────────────────────

function OptionGroup<T extends string | number>({
  options,
  value,
  onChange,
  disabled,
}: {
  options: { value: T; label: string; desc?: string }[]
  value: T
  onChange: (v: T) => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(opt => (
        <button
          key={String(opt.value)}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={`rounded-md border text-label font-medium transition-colors disabled:opacity-50 ${
            opt.desc ? 'flex flex-col px-4 py-2 text-left min-w-30' : 'px-3 py-1.5'
          } ${
            value === opt.value ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-accent'
          }`}
        >
          <span>{opt.label}</span>
          {opt.desc && (
            <span className="mt-0.5 text-label font-normal text-muted-foreground">{opt.desc}</span>
          )}
        </button>
      ))}
    </div>
  )
}

function EmoteChip({
  emote,
  prefix,
  available,
  channelBadges,
}: {
  emote: EmoteItem
  prefix: string
  available: boolean
  channelBadges: ChannelBadges | null
}) {
  const badgeOverlay = getBadgeOverlay(emote, channelBadges)
  const displayName =
    prefix && emote.name.startsWith(prefix) ? emote.name.slice(prefix.length) : emote.name
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={`relative flex select-none flex-col items-center gap-1 rounded-md border border-transparent p-1.5 transition-opacity ${
            available ? '' : 'opacity-40'
          }`}
        >
          {badgeOverlay && (
            <span className="absolute top-1 right-1 rounded-sm bg-black/60 p-0.5">
              <TwitchBadge src={badgeOverlay.src} alt="" size={18} />
            </span>
          )}
          <img
            src={emote.url}
            alt={displayName}
            className="h-14 w-14 object-contain"
            loading="lazy"
          />
          <span className="text-label text-muted-foreground max-w-14 truncate">{displayName}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>
          {emote.name}
          {badgeOverlay && ` (${badgeOverlay.label})`}
          {!available && ' — Bot 無法使用'}
        </p>
      </TooltipContent>
    </Tooltip>
  )
}

function EmoteSection({
  label,
  emotes,
  prefix,
  channelBadges,
}: {
  label: string
  emotes: EmoteItem[]
  prefix: string
  channelBadges: ChannelBadges | null
}) {
  if (emotes.length === 0) return null
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label text-muted-foreground">{label}</span>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] gap-1">
        {emotes.map(emote => (
          <EmoteChip
            key={emote.id}
            emote={emote}
            prefix={prefix}
            available={emote.available}
            channelBadges={channelBadges}
          />
        ))}
      </div>
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

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
    draft.response_lang !== saved.response_lang ||
    draft.refusal_style !== saved.refusal_style ||
    draft.max_tokens !== saved.max_tokens

  const isDefault =
    draft.bot_name === AI_SETTINGS_DEFAULT.bot_name &&
    draft.persona === AI_SETTINGS_DEFAULT.persona &&
    draft.response_lang === AI_SETTINGS_DEFAULT.response_lang &&
    draft.refusal_style === AI_SETTINGS_DEFAULT.refusal_style &&
    draft.max_tokens === AI_SETTINGS_DEFAULT.max_tokens

  const channelPrefix = useMemo(
    () => longestCommonPrefix(emotes.filter(e => e.emote_type !== 'globals').map(e => e.name)),
    [emotes]
  )

  const { followerEmotes, subscriptionEmotes, bitsEmotes, globalEmotes } = useMemo(() => {
    const q = emoteSearch.trim().toLowerCase()
    const match = (e: EmoteItem) => !q || e.name.toLowerCase().includes(q)
    const byName = (arr: EmoteItem[]) => [...arr].sort((a, b) => a.name.localeCompare(b.name))
    const bySub = (arr: EmoteItem[]) =>
      [...arr].sort((a, b) => {
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
    setSaving(true)
    try {
      const updated = await patchAISettings({
        bot_name: draft.bot_name,
        persona: draft.persona,
        response_lang: draft.response_lang,
        refusal_style: draft.refusal_style,
        max_tokens: draft.max_tokens,
      })
      const normalized = { ...updated, enabled_emotes: updated.enabled_emotes ?? [] }
      setSaved(normalized)
      setDraft(normalized)
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

  const disabled = loading || saving
  const totalEmotes =
    followerEmotes.length + subscriptionEmotes.length + bitsEmotes.length + globalEmotes.length

  return (
    <PageMain>
      <PageHeader title="AI 助手" description="Twitch 聊天室 AI 問答指令設定" />

      <SlideUp inView delay={0.05} className="flex flex-col gap-section">
        {/* 2:1 — editable left | reference right */}
        <div className="grid gap-section lg:grid-cols-[2fr_1fr] items-start">
          {/* Left — all editable cards */}
          <div className="flex flex-col gap-section">
            {/* Identity */}
            <Card>
              <CardHeader>
                <CardTitle>身份</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-element">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="bot-name">Bot 名稱</Label>
                  <Input
                    id="bot-name"
                    value={draft.bot_name}
                    onChange={e => patch('bot_name', e.target.value)}
                    maxLength={50}
                    placeholder="Twitch 聊天室機器人"
                    disabled={disabled}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="persona">個性描述</Label>
                    <span className="font-mono text-label text-muted-foreground">
                      {(draft.persona ?? '').length} / 300
                    </span>
                  </div>
                  <textarea
                    id="persona"
                    value={draft.persona ?? ''}
                    onChange={e => patch('persona', e.target.value)}
                    maxLength={300}
                    rows={4}
                    placeholder="幽默風趣、愛開玩笑…（留空代表無特別個性）"
                    disabled={disabled}
                    className="w-full rounded-md border border-input bg-transparent dark:bg-input/30 px-3 py-2 text-label leading-relaxed resize-none shadow-xs focus:outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </div>
              </CardContent>
            </Card>

            {/* Language + Refusal */}
            <Card>
              <CardHeader>
                <CardTitle>語言與風格</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-section">
                <div className="flex flex-col gap-element">
                  <Label>語言</Label>
                  <OptionGroup
                    options={LANG_OPTIONS}
                    value={draft.response_lang}
                    onChange={v => patch('response_lang', v)}
                    disabled={disabled}
                  />
                </div>
                <div className="flex flex-col gap-element">
                  <Label>拒絕風格</Label>
                  <OptionGroup
                    options={REFUSAL_OPTIONS}
                    value={draft.refusal_style}
                    onChange={v => patch('refusal_style', v)}
                    disabled={disabled}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Max tokens */}
            <Card>
              <CardHeader>
                <CardTitle>回應長度</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-element">
                <div className="flex items-center justify-between">
                  <Label>最大 token 數</Label>
                  <span className="font-mono text-label text-muted-foreground">
                    {draft.max_tokens} tokens
                  </span>
                </div>
                <OptionGroup
                  options={MAX_TOKENS_OPTIONS}
                  value={draft.max_tokens}
                  onChange={v => patch('max_tokens', v)}
                  disabled={disabled}
                />
              </CardContent>
            </Card>
          </div>

          {/* Right — reference info + emotes */}
          <div className="flex flex-col gap-section">
            {/* Command info + current model */}
            <Card>
              <CardHeader>
                <CardTitle>指令資訊</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col divide-y">
                  {COMMAND_INFO.map(({ label, value }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between py-2.5 first:pt-0"
                    >
                      <Label className="text-muted-foreground">{label}</Label>
                      <span className="font-mono text-label">{value}</span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between py-2.5 last:pb-0">
                    <Label className="text-muted-foreground">模型</Label>
                    <span className="font-mono text-label truncate max-w-[55%] text-right">
                      {PROVIDERS[0].model}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Emote info */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <CardTitle className="shrink-0">貼圖使用</CardTitle>
                  <Input
                    placeholder="搜尋貼圖…"
                    value={emoteSearch}
                    onChange={e => setEmoteSearch(e.target.value)}
                    className="ml-auto h-7 text-label w-32 shrink-0"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-label text-muted-foreground">
                    右上角徽章表示使用限制；半透明表示 Bot 無法使用
                  </span>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-element">
                {emotesLoading ? (
                  <div className="flex items-center justify-center py-6">
                    <Spinner className="h-5 w-5" />
                  </div>
                ) : totalEmotes === 0 ? (
                  <p className="py-4 text-center text-label text-muted-foreground">
                    找不到符合的貼圖
                  </p>
                ) : (
                  <div className="flex max-h-80 flex-col gap-3 overflow-y-auto rounded-md border p-3">
                    <EmoteSection
                      label="追隨者"
                      emotes={followerEmotes}
                      prefix={channelPrefix}
                      channelBadges={channelBadges}
                    />
                    <EmoteSection
                      label="訂閱"
                      emotes={subscriptionEmotes}
                      prefix={channelPrefix}
                      channelBadges={channelBadges}
                    />
                    <EmoteSection
                      label="Bits"
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
          </div>
        </div>

        {/* Full — Actions */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex gap-2">
            {isDirty && (
              <Button variant="ghost" size="sm" onClick={() => setDraft(saved)} disabled={saving}>
                取消
              </Button>
            )}
            {!isDefault && (
              <Button variant="outline" size="sm" onClick={handleReset} disabled={disabled}>
                {saving ? (
                  <Spinner className="mr-1.5 h-3 w-3" />
                ) : (
                  <Icon icon="fa-solid fa-rotate-left" className="mr-1.5 text-xs" />
                )}
                重設預設值
              </Button>
            )}
          </div>
          <Button size="sm" onClick={handleSave} disabled={!isDirty || disabled}>
            {saving ? (
              <Spinner className="mr-1.5 h-3 w-3" />
            ) : (
              <Icon icon="fa-solid fa-floppy-disk" className="mr-1.5 text-xs" />
            )}
            儲存
          </Button>
        </div>
      </SlideUp>
    </PageMain>
  )
}
