import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'

import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  type BadgeEntry,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Label,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
  SlideUp,
  Switch,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TwitchBadgeGroup,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { copyToClipboard } from '@/lib/clipboard'

import {
  type AlignOption,
  type AnimDirOption,
  type BadgeFilterOption,
  type ChatCssSettings,
  generateCss,
  loadSettings,
  type MsgBgOption,
  saveSettings,
  type SpacingOption,
} from './chatOverlayCss'

// ---- Demo sequence ----

type DemoMsgType = 'chat' | 'reply'

interface DemoMsg {
  id: string
  type: DemoMsgType
  username: string
  color: string
  text: string
  replyTo?: string
  is_mod?: boolean
  is_sub?: boolean
  is_vip?: boolean
  is_broadcaster?: boolean
  delay: number
}

const SEQUENCE: DemoMsg[] = [
  {
    id: 'p1',
    type: 'chat',
    username: 'Alice',
    color: '#6bcbff',
    is_vip: true,
    text: '今天直播啥？',
    delay: 0,
  },
  {
    id: 'b1',
    type: 'chat',
    username: 'Streamer',
    color: '#a970ff',
    is_broadcaster: true,
    text: '今天打 FPS！',
    delay: 160,
  },
  {
    id: 'p2',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    text: 'PogChamp 開始了',
    delay: 400,
  },
  {
    id: 'p3',
    type: 'chat',
    username: 'LoyalFan',
    color: '#c678dd',
    is_sub: true,
    text: '第 12 個月了還在這 Clap',
    delay: 660,
  },
  {
    id: 'p4',
    type: 'reply',
    username: 'Charlie',
    color: '#b5ff6b',
    is_sub: true,
    replyTo: 'Alice',
    text: '他說打遊戲啦',
    delay: 920,
  },
  {
    id: 'b2',
    type: 'chat',
    username: 'Streamer',
    color: '#a970ff',
    is_broadcaster: true,
    text: '準備好了嗎！',
    delay: 1060,
  },
  {
    id: 'p5',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    is_sub: true,
    text: 'gg 開打！LUL',
    delay: 1270,
  },
  { id: 'p6', type: 'chat', username: 'Viewer7', color: '#00e5ff', text: '哈哈哈', delay: 1520 },
  {
    id: 'p7',
    type: 'chat',
    username: 'VIPMember',
    color: '#f7c59f',
    is_vip: true,
    is_sub: true,
    text: '太猛了吧 KEKW',
    delay: 1770,
  },
  {
    id: 'p8',
    type: 'reply',
    username: 'Alice',
    color: '#6bcbff',
    is_vip: true,
    replyTo: 'Charlie',
    text: '對啦打遊戲！',
    delay: 2020,
  },
  {
    id: 'p9',
    type: 'chat',
    username: 'NewViewer',
    color: '#98c379',
    text: '嗨大家好！',
    delay: 2260,
  },
  {
    id: 'b3',
    type: 'chat',
    username: 'Streamer',
    color: '#a970ff',
    is_broadcaster: true,
    text: '歡迎！',
    delay: 2380,
  },
  {
    id: 'p10',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    text: '記得遵守聊天室規則喔',
    delay: 2580,
  },
]

const LOOP_MS = Math.max(...SEQUENCE.map(m => m.delay)) + 2500

// ---- Chat preview ----

function ChatBadges({ msg, filter }: { msg: DemoMsg; filter: BadgeFilterOption }) {
  if (filter === 'none') return null
  const badges: BadgeEntry[] = []
  if (msg.is_broadcaster) badges.push({ role: 'broadcaster' })
  if (msg.is_mod) badges.push({ role: 'moderator' })
  if (msg.is_vip) badges.push({ role: 'vip' })
  if (msg.is_sub && !msg.is_mod && !msg.is_vip && !msg.is_broadcaster)
    badges.push({ role: 'subscriber' })
  return <TwitchBadgeGroup badges={badges} className="mr-1" />
}

function ChatPreview({ s }: { s: ChatCssSettings }) {
  const [{ loopKey, visibleIds }, setLoop] = useState<{
    loopKey: number
    visibleIds: ReadonlySet<string>
  }>({ loopKey: 0, visibleIds: new Set() })
  const isFirstRender = useRef(true)

  // Sequence player — reset and schedule atomically so there's no mid-effect setState
  useEffect(() => {
    const timers = SEQUENCE.map(({ id, delay }) =>
      setTimeout(
        () => setLoop(prev => ({ ...prev, visibleIds: new Set([...prev.visibleIds, id]) })),
        delay
      )
    )
    const next = setTimeout(
      () => setLoop(prev => ({ loopKey: prev.loopKey + 1, visibleIds: new Set() })),
      LOOP_MS
    )
    return () => {
      timers.forEach(clearTimeout)
      clearTimeout(next)
    }
  }, [loopKey])

  // Restart sequence immediately when any visual setting changes
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }
    setLoop(prev => ({ loopKey: prev.loopKey + 1, visibleIds: new Set() }))
  }, [
    s.background,
    s.bgColor,
    s.fontSize,
    s.spacing,
    s.messageBg,
    s.align,
    s.badgeFilter,
    s.textShadow,
    s.animation,
    s.animDir,
    s.hideBot,
  ])

  // Determine if picked color is light (for text contrast)
  const isLightBg =
    s.background === 'color' &&
    (() => {
      const hex = s.bgColor.replace('#', '')
      const r = parseInt(hex.slice(0, 2), 16)
      const g = parseInt(hex.slice(2, 4), 16)
      const b = parseInt(hex.slice(4, 6), 16)
      return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5
    })()

  const textColor = isLightBg ? '#111' : '#fff'
  const previewBg = s.background === 'color' ? s.bgColor : '#5aab6e'
  const fontSize = `${s.fontSize}px`
  const shadow = s.textShadow ? '1px 1px 3px rgba(0,0,0,0.9)' : undefined

  const chatBg = useMemo<React.CSSProperties>(
    () =>
      s.messageBg === 'dark'
        ? { background: 'rgba(0,0,0,0.52)', padding: '3px 10px', borderRadius: '4px' }
        : s.messageBg === 'rounded'
          ? { background: 'rgba(0,0,0,0.62)', padding: '5px 12px', borderRadius: '12px' }
          : { padding: '1px 0' },
    [s.messageBg]
  )

  const msgBase = useMemo<React.CSSProperties>(
    () => ({
      fontFamily: 'Tahoma, Arial, sans-serif',
      fontSize,
      lineHeight: '1.5',
      color: textColor,
      wordBreak: 'break-word',
      overflowWrap: 'break-word',
    }),
    [fontSize, textColor]
  )

  function renderMsg(msg: DemoMsg): React.ReactNode {
    if (s.messageBg === 'bubble') {
      const isRight = msg.is_broadcaster ? s.align !== 'right' : s.align === 'right'
      const bubbleRadius = isRight ? '14px 3px 14px 14px' : '3px 14px 14px 14px'
      // Username floats on the background — always needs shadow for legibility
      const usernameShadow = '0 1px 3px rgba(0,0,0,0.85), 0 1px 6px rgba(0,0,0,0.6)'
      return (
        <div
          style={{
            ...msgBase,
            display: 'flex',
            flexDirection: 'column',
            alignItems: isRight ? 'flex-end' : 'flex-start',
          }}
        >
          {msg.type === 'reply' && (
            <div
              style={{
                fontSize: '0.7em',
                marginBottom: 2,
                textShadow: usernameShadow,
                opacity: 0.7,
              }}
            >
              {'↩'} @{msg.replyTo}
            </div>
          )}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'nowrap',
              overflow: 'hidden',
              gap: 3,
              fontSize: '0.78em',
              maxWidth: '90%',
              marginBottom: 3,
            }}
          >
            <ChatBadges msg={msg} filter={s.badgeFilter} />
            <span style={{ fontWeight: 700, color: msg.color, textShadow: usernameShadow }}>
              {msg.username}
            </span>
          </div>
          <div
            style={{
              background: 'rgba(0,0,0,0.68)',
              borderRadius: bubbleRadius,
              padding: '8px 14px',
              maxWidth: '90%',
              color: '#fff',
              textShadow: shadow,
            }}
          >
            {msg.text}
          </div>
        </div>
      )
    }

    // Non-bubble: alignment wrapper so the message box hugs content while staying positioned
    const alignWrap: React.CSSProperties = {
      display: 'flex',
      justifyContent: s.align === 'right' ? 'flex-end' : 'flex-start',
    }

    if (msg.type === 'reply') {
      return (
        <div style={alignWrap}>
          <div style={{ ...msgBase, ...chatBg, maxWidth: '100%' }}>
            <div style={{ fontSize: '0.78em', opacity: 0.4, marginBottom: 2 }}>
              {'↩'} @{msg.replyTo}
            </div>
            <div>
              <span
                style={{ display: 'inline-flex', alignItems: 'center', verticalAlign: 'middle' }}
              >
                <ChatBadges msg={msg} filter={s.badgeFilter} />
              </span>
              <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
              <span style={{ opacity: 0.55 }}>: </span>
              <span style={{ textShadow: shadow }}>{msg.text}</span>
            </div>
          </div>
        </div>
      )
    }
    return (
      <div style={alignWrap}>
        <div style={{ ...msgBase, ...chatBg, maxWidth: '100%' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', verticalAlign: 'middle' }}>
            <ChatBadges msg={msg} filter={s.badgeFilter} />
          </span>
          <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
          <span style={{ opacity: 0.55 }}>: </span>
          <span style={{ textShadow: shadow }}>{msg.text}</span>
        </div>
      </div>
    )
  }

  const visible = SEQUENCE.filter(m => visibleIds.has(m.id)).slice(-10)

  return (
    <div
      style={{
        background: previewBg,
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        padding: '10px',
        boxSizing: 'border-box',
        gap: { compact: '4px', normal: '8px', loose: '16px' }[s.spacing],
        overflow: 'hidden',
      }}
    >
      {visible.map(msg => (
        <motion.div
          key={`${msg.id}-${loopKey}`}
          initial={s.animation ? { opacity: 0, x: s.animDir === 'left' ? -10 : 10 } : false}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          style={{ flexShrink: 0, minWidth: 0, width: '100%' }}
        >
          {renderMsg(msg)}
        </motion.div>
      ))}
    </div>
  )
}

// ---- CSS Syntax Highlighter ----

const C = {
  comment: 'hsl(220 10% 52%)',
  atRule: 'hsl(270 65% 72%)',
  selector: 'hsl(200 75% 62%)',
  property: 'hsl(175 55% 58%)',
  value: 'hsl(40 10% 82%)',
  important: 'hsl(30 85% 62%)',
  punctuation: 'hsl(220 10% 50%)',
}

function HLine({ line }: { line: string }) {
  const trimmed = line.trimStart()
  const indent = line.slice(0, line.length - trimmed.length)

  if (!trimmed) return <>{line}</>

  // Comment
  if (trimmed.startsWith('/*')) {
    return <span style={{ color: C.comment, fontStyle: 'italic' }}>{line}</span>
  }

  // Closing brace
  if (trimmed === '}') {
    return (
      <>
        <span>{indent}</span>
        <span style={{ color: C.punctuation }}>{'}'}</span>
      </>
    )
  }

  // At-rule keyword (@keyframes name {)
  if (trimmed.startsWith('@')) {
    const m = line.match(/^(\s*)(@[\w-]+)([^{]*)(\{?)$/)
    if (m)
      return (
        <>
          {m[1]}
          <span style={{ color: C.atRule }}>{m[2]}</span>
          <span style={{ color: C.value }}>{m[3]}</span>
          {m[4] && <span style={{ color: C.punctuation }}>{m[4]}</span>}
        </>
      )
  }

  // from / to lines (inside @keyframes)
  if (/^\s*(from|to)\s*\{/.test(line)) {
    const m = line.match(/^(\s*)(from|to)(\s*)(\{)(.*)(\})/)
    if (m)
      return (
        <>
          {m[1]}
          <span style={{ color: C.atRule }}>{m[2]}</span>
          {m[3]}
          <span style={{ color: C.punctuation }}>{m[4]}</span>
          <span style={{ color: C.value }}>{m[5]}</span>
          <span style={{ color: C.punctuation }}>{m[6]}</span>
        </>
      )
  }

  // Selector line — ends with { or ,
  if (trimmed.endsWith('{') || trimmed.endsWith(',')) {
    const m = line.match(/^(.*?)([{,])\s*$/)
    if (m)
      return (
        <>
          <span style={{ color: C.selector }}>{m[1]}</span>
          <span style={{ color: C.punctuation }}>{m[2]}</span>
        </>
      )
  }

  // Property: value !important;
  const propM = line.match(/^(\s*)([\w-]+)(\s*:\s*)(.*?)(\s*!important)?(;)(\s*)$/)
  if (propM) {
    const [, ind, prop, colon, val, imp, semi] = propM
    return (
      <>
        {ind}
        <span style={{ color: C.property }}>{prop}</span>
        <span style={{ color: C.punctuation }}>{colon}</span>
        <span style={{ color: C.value }}>{val}</span>
        {imp && <span style={{ color: C.important }}>{imp}</span>}
        <span style={{ color: C.punctuation }}>{semi}</span>
      </>
    )
  }

  return <>{line}</>
}

function CssHighlight({ code }: { code: string }) {
  const lines = code.split('\n')
  return (
    <pre className="text-label leading-relaxed whitespace-pre">
      {lines.map((line, i) => (
        <React.Fragment key={i}>
          <HLine line={line} />
          {i < lines.length - 1 && '\n'}
        </React.Fragment>
      ))}
    </pre>
  )
}

// ---- Option button group ----

function OptionButtonGroup<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
  labelClassName,
}: {
  label: string
  options: { value: T; label: string; desc?: string }[]
  value: T
  onChange: (v: T) => void
  className?: string
  labelClassName?: string
}) {
  return (
    <div className={`flex flex-col gap-2${className ? ` ${className}` : ''}`}>
      <Label className={labelClassName}>{label}</Label>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-md border text-sub font-medium transition-colors ${
              opt.desc ? 'flex flex-col px-4 py-2 text-left' : 'px-3 py-1.5'
            } ${
              value === opt.value ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-accent'
            }`}
          >
            {opt.desc ? (
              <>
                <span className="font-medium">{opt.label}</span>
                <span className="text-muted-foreground text-label">{opt.desc}</span>
              </>
            ) : (
              opt.label
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

// ---- Step Slider ----

function StepSlider<T extends string | number>({
  label,
  steps,
  value,
  onChange,
  unit,
}: {
  label: string
  steps: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  unit?: string
}) {
  const idx = Math.max(
    0,
    steps.findIndex(s => s.value === value)
  )
  const current = steps[idx]
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <span className="font-mono text-label text-muted-foreground">
          {current.label}
          {unit ? ` · ${current.value}${unit}` : ''}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={steps.length - 1}
        step={1}
        value={idx}
        onChange={e => onChange(steps[+e.target.value].value)}
        style={{ accentColor: 'var(--color-primary)' }}
        className="w-full cursor-pointer"
      />
      <div className="flex justify-between">
        {steps.map((s, i) => (
          <span
            key={i}
            onClick={() => onChange(s.value)}
            className={`cursor-pointer select-none text-[10px] leading-none transition-colors ${
              i === idx
                ? 'text-primary font-semibold'
                : 'text-muted-foreground/50 hover:text-muted-foreground'
            }`}
          >
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ---- Page ----

// Aligned to index.css semantic type scale: xs/sm/base/lg/xl/2xl
const FONT_SIZE_STEPS: { value: number; label: string }[] = [
  { value: 12, label: 'xs' },
  { value: 14, label: 'sm' },
  { value: 16, label: 'base' },
  { value: 18, label: 'lg' },
  { value: 20, label: 'xl' },
  { value: 24, label: '2xl' },
]

const SPACING_STEPS: { value: SpacingOption; label: string }[] = [
  { value: 'compact', label: '緊湊' },
  { value: 'normal', label: '標準' },
  { value: 'loose', label: '寬鬆' },
]

const MSG_BG_OPTIONS: { value: MsgBgOption; label: string }[] = [
  { value: 'bubble', label: '氣泡' },
  { value: 'rounded', label: '深色圓框' },
  { value: 'dark', label: '深色方框' },
  { value: 'none', label: '無' },
]

const ALIGN_OPTIONS: { value: AlignOption; label: string }[] = [
  { value: 'left', label: '靠左' },
  { value: 'right', label: '靠右' },
]

const ANIM_DIR_OPTIONS: { value: AnimDirOption; label: string }[] = [
  { value: 'left', label: '從左' },
  { value: 'right', label: '從右' },
]

const BADGE_FILTER_OPTIONS: { value: BadgeFilterOption; label: string; desc?: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'role-sub', label: '角色+訂閱' },
  { value: 'none', label: '隱藏' },
]

export default function ChatOverlayModule() {
  useDocumentTitle('Chat Overlay')

  const { user } = useAuth()
  const [settings, setSettings] = useState<ChatCssSettings>(loadSettings)
  const [rightPanel, setRightPanel] = useState<'preview' | 'css'>('preview')
  const [settingsOpen, setSettingsOpen] = useState(false)

  const patch = useCallback((partial: Partial<ChatCssSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...partial }
      // text shadow only applies to transparent backgrounds — reset when leaving transparent
      if (partial.background && partial.background !== 'transparent') next.textShadow = false
      return next
    })
  }, [])

  useEffect(() => {
    saveSettings(settings)
  }, [settings])

  const css = useMemo(() => generateCss(settings), [settings])

  const copyCss = () => copyToClipboard(css, 'CSS 已複製', '複製失敗，請手動選取')

  const twitchUrl = user?.name ? `https://www.twitch.tv/popout/${user.name}/chat` : ''

  return (
    <PageMain>
      <PageHeader
        title="Chat Overlay"
        description="自訂 Twitch 聊天室樣式，貼入 OBS Browser Source"
      >
        <Button
          variant="ghost"
          size="icon"
          className="mt-0.5 shrink-0 border border-primary/40 text-muted-foreground hover:border-primary hover:text-primary/80"
          onClick={() => setSettingsOpen(true)}
          title="使用說明"
        >
          <Icon
            icon="fa-regular fa-circle-question"
            wrapperClassName="size-5"
            className="text-content"
          />
        </Button>
      </PageHeader>

      {/* Help sheet */}
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>Chat Overlay 使用說明</SheetTitle>
            <SheetDescription>如何在 OBS 套用自訂聊天室樣式</SheetDescription>
          </SheetHeader>
          <SheetSection className="flex flex-col flex-1 overflow-y-auto">
            {/* Step 1 — 調整樣式 */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-solid fa-palette"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
                <div className="mt-1 w-px flex-1 bg-border" />
              </div>
              <div className="flex flex-col gap-element pb-6">
                <p className="text-content font-semibold">調整樣式</p>
                <p className="text-sub text-muted-foreground">
                  在右側設定面板調整外觀，左側預覽即時更新。
                </p>
                <ul className="flex flex-col gap-1">
                  {[
                    '外觀：背景透明或自訂色、訊息樣式、對齊方向',
                    '文字：字型大小與行間距',
                    '顯示：隱藏標題列、徽章、文字陰影',
                    '動畫：進場方向',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Step 2 — 複製 CSS */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-solid fa-code"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
                <div className="mt-1 w-px flex-1 bg-border" />
              </div>
              <div className="flex flex-col gap-element pb-6">
                <p className="text-content font-semibold">複製 CSS</p>
                <p className="text-sub text-muted-foreground">取得產生的樣式表貼入 OBS。</p>
                <ul className="flex flex-col gap-1">
                  {['切換到「CSS」分頁', '點擊「複製 CSS」按鈕'].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Step 3 — OBS 設定 */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-solid fa-display"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-element pb-2">
                <p className="text-content font-semibold">OBS 加入 Browser Source</p>
                <p className="text-sub text-muted-foreground">
                  將聊天室以透明 overlay 疊加到畫面上。
                </p>
                <ul className="flex flex-col gap-1">
                  {[
                    'OBS 新增瀏覽器來源',
                    'URL 填入下方 Twitch 聊天室連結',
                    '將複製的 CSS 貼入「自訂 CSS」欄位',
                    '建議尺寸 360 × 640 px',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </SheetSection>
        </SheetContent>
      </Sheet>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-12 gap-section items-start"
      >
        {/* Left: switchable Preview / CSS */}
        <div className="lg:col-span-6 flex flex-col gap-element min-w-0">
          {/* Tab bar */}
          <div className="flex shrink-0 items-center">
            <div className="flex gap-1 rounded-lg border p-1">
              {(['preview', 'css'] as const).map(panel => (
                <button
                  key={panel}
                  type="button"
                  onClick={() => setRightPanel(panel)}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sub font-medium transition-colors ${
                    rightPanel === panel
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon
                    icon={panel === 'preview' ? 'fa-solid fa-eye' : 'fa-solid fa-code'}
                    className="text-label"
                  />
                  {panel === 'preview' ? '預覽' : 'CSS'}
                </button>
              ))}
            </div>
          </div>

          {/* Panel content */}
          {rightPanel === 'preview' ? (
            <>
              <div className="flex justify-center">
                <div
                  className="overflow-hidden rounded-lg border w-full max-w-[360px]"
                  style={{ aspectRatio: '360/640' }}
                >
                  <ChatPreview s={settings} />
                </div>
              </div>
              {twitchUrl && <OverlayUrlBlock url={twitchUrl} />}
            </>
          ) : (
            <div className="h-[462px] overflow-auto rounded-lg border bg-muted p-4">
              <CssHighlight code={css} />
            </div>
          )}
        </div>

        {/* Right: Settings */}
        <div className="lg:col-span-6 flex flex-col gap-section">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <div className="flex flex-col gap-1">
                <CardTitle>樣式設定</CardTitle>
                <CardDescription>調整後自動產生 CSS，無需儲存</CardDescription>
              </div>
              <Button onClick={copyCss} size="sm" className="shrink-0">
                <Icon icon="fa-regular fa-copy" className="mr-1.5 text-label" />
                複製 CSS
              </Button>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* ── 外觀 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">外觀</p>
                <div className="flex flex-col gap-2">
                  <Label>背景</Label>
                  <div className="flex items-center gap-2">
                    {(['transparent', 'color'] as const).map(opt => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => patch({ background: opt })}
                        className={`select-none rounded-md border px-3 py-1.5 text-sub font-medium transition-colors ${
                          settings.background === opt
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'hover:bg-accent'
                        }`}
                      >
                        {opt === 'transparent' ? '透明' : '顏色'}
                      </button>
                    ))}
                    {settings.background === 'color' && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <label className="cursor-pointer select-none">
                            <span
                              className="block w-7 h-7 rounded-md border border-border transition-transform hover:scale-110"
                              style={{ background: settings.bgColor }}
                            />
                            <input
                              type="color"
                              value={settings.bgColor}
                              onChange={e => patch({ bgColor: e.target.value })}
                              className="sr-only"
                            />
                          </label>
                        </TooltipTrigger>
                        <TooltipContent>選擇背景顏色</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-section">
                  <OptionButtonGroup
                    label="樣式"
                    options={MSG_BG_OPTIONS}
                    value={settings.messageBg}
                    onChange={v => patch({ messageBg: v })}
                  />
                  <OptionButtonGroup
                    label="對齊"
                    options={ALIGN_OPTIONS}
                    value={settings.align}
                    onChange={v => patch({ align: v })}
                  />
                </div>
              </div>

              {/* ── 文字 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">文字</p>
                <div className="grid grid-cols-2 gap-section">
                  <StepSlider
                    label="大小"
                    steps={FONT_SIZE_STEPS}
                    value={settings.fontSize}
                    onChange={v => patch({ fontSize: v })}
                    unit="px"
                  />
                  <StepSlider
                    label="間距"
                    steps={SPACING_STEPS}
                    value={settings.spacing}
                    onChange={v => patch({ spacing: v })}
                  />
                </div>
              </div>

              {/* ── 顯示 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">顯示</p>
                <div className="flex flex-col gap-element">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="hideHeader">隱藏標題列</Label>
                    <Switch
                      id="hideHeader"
                      checked={settings.hideHeader}
                      onCheckedChange={v => patch({ hideHeader: v })}
                    />
                  </div>
                  <OptionButtonGroup
                    label="徽章顯示"
                    options={BADGE_FILTER_OPTIONS}
                    value={settings.badgeFilter}
                    onChange={v => patch({ badgeFilter: v })}
                  />
                  {settings.background === 'transparent' && (
                    <div className="flex items-center justify-between">
                      <div>
                        <Label htmlFor="textShadow">文字陰影</Label>
                        <p className="text-muted-foreground mt-0.5 text-label">增強文字辨識度</p>
                      </div>
                      <Switch
                        id="textShadow"
                        checked={settings.textShadow}
                        onCheckedChange={v => patch({ textShadow: v })}
                      />
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label htmlFor="hideBot">隱藏 Bot 訊息</Label>
                      <p className="text-muted-foreground mt-0.5 text-label">依機器人徽章過濾</p>
                    </div>
                    <Switch
                      id="hideBot"
                      checked={settings.hideBot}
                      onCheckedChange={v => patch({ hideBot: v })}
                    />
                  </div>
                </div>
              </div>

              {/* ── 動畫 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">動畫</p>
                <div className="flex flex-col gap-element">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="animation">進場動畫</Label>
                    <Switch
                      id="animation"
                      checked={settings.animation}
                      onCheckedChange={v => patch({ animation: v })}
                    />
                  </div>
                  {settings.animation && (
                    <OptionButtonGroup
                      label="方向"
                      options={ANIM_DIR_OPTIONS}
                      value={settings.animDir}
                      onChange={v => patch({ animDir: v })}
                      labelClassName="text-muted-foreground"
                    />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </SlideUp>
    </PageMain>
  )
}
