import { type Dispatch, type SetStateAction, useMemo, useState } from 'react'

import type { AISettings } from '@/api/aiSettings'
import { AI_SETTINGS_DEFAULT } from '@/api/aiSettings'
import type { ChannelBadges } from '@/api/analytics'
import type { EmoteItem } from '@/api/emotes'
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

import {
  CATCHPHRASE_FREQUENCY_OPTIONS,
  COMMAND_INFO,
  LANG_OPTIONS,
  PERSONA_PRESETS,
  REFUSAL_OPTIONS,
  ROLE_OPTIONS,
  TONE_OPTIONS,
} from './constants'
import { EmoteSection } from './EmoteSection'
import { longestCommonPrefix } from './utils'

interface PersonaPanelProps {
  saved: AISettings
  draft: AISettings
  setDraft: Dispatch<SetStateAction<AISettings>>
  patch: <K extends keyof AISettings>(key: K, value: AISettings[K]) => void
  loading: boolean
  saving: boolean
  twitchModel: string | null | undefined
  emotes: EmoteItem[]
  emotesLoading: boolean
  channelBadges: ChannelBadges | null
  onSave: () => void
  onReset: () => void
  onCommandSave: () => void
  onToggleEnabled: (value: boolean) => void
  onUsePersona: () => void
}

export function PersonaPanel({
  saved,
  draft,
  setDraft,
  patch,
  loading,
  saving,
  twitchModel,
  emotes,
  emotesLoading,
  channelBadges,
  onSave,
  onReset,
  onCommandSave,
  onToggleEnabled,
  onUsePersona,
}: PersonaPanelProps) {
  const [emoteSearch, setEmoteSearch] = useState('')
  const disabled = loading || saving

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
    const query = emoteSearch.trim().toLowerCase()
    const matches = (emote: EmoteItem) => !query || emote.name.toLowerCase().includes(query)
    const animatedFirst = (left: EmoteItem, right: EmoteItem) =>
      left.animated === right.animated ? 0 : left.animated ? 1 : -1
    const byName = (items: EmoteItem[]) =>
      [...items].sort(
        (left, right) => animatedFirst(left, right) || left.name.localeCompare(right.name)
      )
    const bySubscription = (items: EmoteItem[]) =>
      [...items].sort((left, right) => {
        const animated = animatedFirst(left, right)
        if (animated !== 0) return animated
        const tier = (parseInt(left.tier) || 0) - (parseInt(right.tier) || 0)
        return tier !== 0 ? tier : left.name.localeCompare(right.name)
      })
    return {
      followerEmotes: byName(
        emotes.filter(emote => emote.emote_type === 'follower' && matches(emote))
      ),
      subscriptionEmotes: bySubscription(
        emotes.filter(emote => emote.emote_type === 'subscriptions' && matches(emote))
      ),
      bitsEmotes: byName(emotes.filter(emote => emote.emote_type === 'bitstier' && matches(emote))),
      globalEmotes: byName(
        emotes.filter(emote => emote.emote_type === 'globals' && matches(emote))
      ),
    }
  }, [emotes, emoteSearch])

  const totalEmotes =
    followerEmotes.length + subscriptionEmotes.length + bitsEmotes.length + globalEmotes.length

  return (
    <div className="flex flex-col gap-section">
      {saved.assistant_mode === 'roleplay' && (
        <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sub font-medium">目前仍由故事角色回覆</p>
            <p className="mt-1 text-label text-muted-foreground">
              編輯或儲存說話風格不會自動中止角色演繹。
            </p>
          </div>
          <Button variant="outline" onClick={onUsePersona} disabled={saving}>
            改用說話風格
          </Button>
        </div>
      )}

      <div className="grid items-start gap-section lg:grid-cols-[2fr_1fr]">
        <SlideUp inView className="flex flex-col gap-section">
          <Card>
            <CardHeader>
              <CardTitle>說話風格</CardTitle>
              <CardAction>
                <Button size="sm" onClick={onSave} disabled={!isDirty || disabled}>
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
              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label>風格範本</Label>
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
                      onClick={() => setDraft(previous => ({ ...previous, ...preset.values }))}
                      className="flex min-w-24 shrink-0 select-none flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left transition-colors hover:bg-accent disabled:opacity-50"
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

              <div className="grid grid-cols-1 gap-section sm:grid-cols-2">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="bot-name">Bot 名稱</Label>
                  <Input
                    id="bot-name"
                    value={draft.bot_name}
                    onChange={event => patch('bot_name', event.target.value)}
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
                    onChange={event => patch('self_pronoun', event.target.value)}
                    maxLength={20}
                    placeholder="我"
                    disabled={disabled}
                  />
                </div>
              </div>
              <p className="text-label text-muted-foreground">
                自稱只在句意需要時使用，不會要求每則回覆固定出現。
              </p>

              <Separator />

              <div className="grid grid-cols-1 gap-section sm:grid-cols-[1fr_1.35fr]">
                <div className="flex flex-col gap-element">
                  <Label htmlFor="catchphrase">口頭禪</Label>
                  <Input
                    id="catchphrase"
                    value={draft.catchphrase}
                    onChange={event => patch('catchphrase', event.target.value)}
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
                    onChange={value => patch('catchphrase_frequency', value)}
                    disabled={disabled || !draft.catchphrase.trim()}
                  />
                  <p className="text-label text-muted-foreground">
                    這是使用傾向，不是精準比例；需要自然回覆時建議選「不使用」。
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-element">
                <div className="flex items-center justify-between">
                  <Label htmlFor="persona" className="text-content font-semibold">
                    個性描述
                  </Label>
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
                  onChange={event => patch('persona', event.target.value)}
                  maxLength={300}
                  rows={3}
                  placeholder="例如：反應俐落，先回答；情境輕鬆時偶爾善意吐槽"
                  disabled={disabled}
                  className="resize-none leading-relaxed"
                />
              </div>

              <div className="flex flex-col gap-element">
                <div className="flex flex-col gap-0.5">
                  <Label className="text-content font-semibold">示例回覆</Label>
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
                  onChange={value => patch('tone_preset', value)}
                  disabled={disabled}
                />
              </div>

              <SettingRow title="回覆語言" description="「跟隨提問」會依每次問題使用的語言回答">
                <OptionPicker
                  options={LANG_OPTIONS}
                  value={draft.response_lang}
                  onChange={value => patch('response_lang', value)}
                  disabled={disabled}
                />
              </SettingRow>

              <div className="flex flex-col gap-element">
                <Label>婉拒方式</Label>
                <OptionPicker
                  options={REFUSAL_OPTIONS}
                  value={draft.refusal_style}
                  onChange={value => patch('refusal_style', value)}
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
                      setDraft(previous => ({
                        ...previous,
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
                  <Button variant="outline" size="sm" onClick={onReset} disabled={disabled}>
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

        <SlideUp inView delay={0.05} className="flex flex-col gap-section">
          <Card>
            <CardHeader>
              <CardTitle>指令設定</CardTitle>
              <CardAction className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-label text-muted-foreground">
                  {saved.enabled ? '啟用中' : '已停用'}
                </span>
                <Switch
                  checked={saved.enabled}
                  onCheckedChange={onToggleEnabled}
                  disabled={loading}
                />
                <div className="h-4 w-px bg-border" />
                {isCmdDirty && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setDraft(previous => ({
                        ...previous,
                        cooldown: saved.cooldown,
                        min_role: saved.min_role,
                      }))
                    }
                    disabled={saving}
                  >
                    取消
                  </Button>
                )}
                <Button size="sm" onClick={onCommandSave} disabled={!isCmdDirty || disabled}>
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
                  <span className="max-w-[55%] truncate text-right font-mono text-label">
                    {twitchModel ?? '—'}
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
                    onChange={event => {
                      const value = parseInt(event.target.value)
                      if (!isNaN(value)) patch('cooldown', Math.max(5, Math.min(300, value)))
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
                  onChange={value => patch('min_role', value)}
                  disabled={disabled}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>我的貼圖</CardTitle>
              <CardAction>
                <Input
                  placeholder="搜尋貼圖…"
                  value={emoteSearch}
                  onChange={event => setEmoteSearch(event.target.value)}
                  className="h-7 w-32 text-label"
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
                  {Array.from({ length: 16 }).map((_, index) => (
                    <div key={index} className="flex flex-col items-center gap-1 p-1.5">
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
    </div>
  )
}
