import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { toast } from 'sonner'

import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
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
  SlideUp,
  SlideUpSm,
  Switch,
  TwitchBadgeGroup,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ---- Types ----

type BgOption = 'transparent' | 'dark' | 'light'
type FontSizeOption = 'small' | 'medium' | 'large'
type SpacingOption = 'compact' | 'normal' | 'loose'
type MsgBgOption = 'none' | 'dark' | 'rounded'
type AlignOption = 'left' | 'right'
type AnimDirOption = 'left' | 'right'

interface ChatCssSettings {
  background: BgOption
  fontSize: FontSizeOption
  spacing: SpacingOption
  messageBg: MsgBgOption
  align: AlignOption
  hideHeader: boolean
  hideInput: boolean
  hideTimestamp: boolean
  hideBadges: boolean
  textShadow: boolean
  animation: boolean
  animDir: AnimDirOption
}

const DEFAULT_SETTINGS: ChatCssSettings = {
  background: 'transparent',
  fontSize: 'medium',
  spacing: 'normal',
  messageBg: 'dark',
  align: 'left',
  hideHeader: true,
  hideInput: true,
  hideTimestamp: true,
  hideBadges: false,
  textShadow: false,
  animation: true,
  animDir: 'left',
}

const STORAGE_KEY = 'niibot:chat-overlay-css'

function loadSettings(): ChatCssSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }
  } catch {
    // ignore JSON parse errors — fall back to defaults
  }
  return DEFAULT_SETTINGS
}

// ---- CSS Generator ----

function generateCss(s: ChatCssSettings): string {
  const parts: string[] = []

  parts.push('/* Twitch Chat Override — 貼入 OBS Browser Source > Custom CSS */')

  const bg =
    s.background === 'dark'
      ? 'rgba(14, 14, 14, 0.85)'
      : s.background === 'light'
        ? 'rgba(240, 240, 240, 0.90)'
        : 'transparent'

  parts.push(`body {\n  background-color: ${bg} !important;\n  overflow: hidden !important;\n}`)

  if (s.hideHeader) {
    parts.push(`.chat-header,\n.stream-chat-header {\n  display: none !important;\n}`)
  }

  if (s.hideInput) {
    parts.push(`.chat-input-section {\n  display: none !important;\n}`)
  }

  if (s.hideBadges) {
    parts.push(`.chat-badge {\n  display: none !important;\n}`)
  }

  const fontSize = { small: '13px', medium: '15px', large: '18px' }[s.fontSize]
  const marginY = { compact: '1px', normal: '2px', loose: '5px' }[s.spacing]
  const [msgBg, msgPad, msgRadius] =
    s.messageBg === 'dark'
      ? ['rgba(0, 0, 0, 0.60)', '4px 8px', '4px']
      : s.messageBg === 'rounded'
        ? ['rgba(0, 0, 0, 0.75)', '5px 10px', '6px']
        : ['transparent', '2px 4px', '0']

  parts.push(
    `.chat-line__message {\n  font-size: ${fontSize} !important;\n  background: ${msgBg} !important;\n  padding: ${msgPad} !important;\n  border-radius: ${msgRadius} !important;\n  margin: ${marginY} 0 !important;\n}`
  )

  if (s.hideTimestamp) {
    parts.push(`.chat-line__timestamp {\n  display: none !important;\n}`)
  }

  if (s.textShadow) {
    parts.push(
      `.chat-line__message * {\n  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.9) !important;\n}`
    )
  }

  if (s.align === 'right') {
    parts.push(
      `.chat-list,\n.chat-list--default {\n  align-items: flex-end !important;\n}\n\n.chat-line__message {\n  text-align: right !important;\n}`
    )
  }

  if (s.animation) {
    const fromX = s.animDir === 'left' ? '-10px' : '10px'
    parts.push(
      `@keyframes niiChatIn {\n  from { opacity: 0; transform: translateX(${fromX}); }\n  to   { opacity: 1; transform: translateX(0); }\n}\n\n.chat-line__message {\n  animation: niiChatIn 0.2s ease-out !important;\n}`
    )
  }

  return parts.join('\n\n')
}

// ---- Demo sequence ----

type DemoMsgType = 'chat' | 'reply' | 'sub' | 'resub' | 'gift-sub' | 'redemption' | 'raid'

interface DemoMsg {
  id: string
  type: DemoMsgType
  username: string
  color: string
  text?: string
  replyTo?: string
  detail?: string
  is_mod?: boolean
  is_sub?: boolean
  is_vip?: boolean
  delay: number
}

const SEQUENCE: DemoMsg[] = [
  // — 開場閒聊 —
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
    id: 'p2',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    text: 'PogChamp 開始了',
    delay: 280,
  },
  {
    id: 'p3',
    type: 'chat',
    username: 'LoyalFan',
    color: '#c678dd',
    is_sub: true,
    text: '第 12 個月了還在這 Clap',
    delay: 540,
  },
  {
    id: 'p4',
    type: 'reply',
    username: 'Charlie',
    color: '#b5ff6b',
    is_sub: true,
    replyTo: 'Alice',
    text: '他說打遊戲啦',
    delay: 800,
  },
  // — 訂閱事件 —
  {
    id: 'p5',
    type: 'sub',
    username: 'NewSubscriber',
    color: '#c678dd',
    detail: 'Tier 1',
    delay: 1500,
  },
  {
    id: 'p6',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    text: 'Clap Clap 歡迎訂閱！',
    delay: 1800,
  },
  {
    id: 'p7',
    type: 'resub',
    username: 'LoyalFan',
    color: '#c678dd',
    detail: '12 個月',
    delay: 2300,
  },
  {
    id: 'p8',
    type: 'chat',
    username: 'Alice',
    color: '#6bcbff',
    is_vip: true,
    text: '哇 12 個月！感謝支持',
    delay: 2600,
  },
  // — 贈訂與兌換 —
  { id: 'p9', type: 'gift-sub', username: 'GiftKing', color: '#e5c07b', detail: '5', delay: 3200 },
  {
    id: 'p10',
    type: 'redemption',
    username: 'Fan99',
    color: '#ff6b6b',
    is_sub: true,
    text: '一路向北',
    detail: '點歌請求',
    delay: 3850,
  },
  // — 頻繁聊天 —
  {
    id: 'p11',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    is_sub: true,
    text: '我的歌！ LUL',
    delay: 4150,
  },
  {
    id: 'p12',
    type: 'chat',
    username: 'Charlie',
    color: '#b5ff6b',
    is_sub: true,
    text: 'LULW LULW',
    delay: 4300,
  },
  { id: 'p13', type: 'chat', username: 'Viewer7', color: '#00e5ff', text: '哈哈哈', delay: 4450 },
  {
    id: 'p14',
    type: 'chat',
    username: 'VIPMember',
    color: '#f7c59f',
    is_vip: true,
    is_sub: true,
    text: '太猛了吧 KEKW',
    delay: 4600,
  },
  // — 突襲 —
  { id: 'p15', type: 'raid', username: 'RaidBoss', color: '#ff6b6b', detail: '50', delay: 5400 },
  {
    id: 'p16',
    type: 'chat',
    username: 'NewRaider',
    color: '#98c379',
    text: '嗨大家好！',
    delay: 5750,
  },
  {
    id: 'p17',
    type: 'chat',
    username: 'Alice',
    color: '#6bcbff',
    is_vip: true,
    text: '歡迎突襲！',
    delay: 5980,
  },
  {
    id: 'p18',
    type: 'chat',
    username: 'Bob',
    color: '#ff9f43',
    is_mod: true,
    text: '記得遵守聊天室規則喔',
    delay: 6200,
  },
]

const LOOP_MS = Math.max(...SEQUENCE.map(m => m.delay)) + 2500

// ---- Chat preview ----

function ChatBadges({ msg, hidden }: { msg: DemoMsg; hidden: boolean }) {
  if (hidden) return null
  const badges: BadgeEntry[] = []
  if (msg.is_mod) badges.push({ role: 'moderator' })
  if (msg.is_vip) badges.push({ role: 'vip' })
  if (msg.is_sub && !msg.is_mod && !msg.is_vip) badges.push({ role: 'subscriber' })
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
    s.fontSize,
    s.spacing,
    s.messageBg,
    s.align,
    s.hideBadges,
    s.textShadow,
    s.animation,
    s.animDir,
  ])

  // Styles derived from current settings
  const textColor = s.background === 'light' ? '#111' : '#fff'
  const fontSize = { small: '11px', medium: '13px', large: '16px' }[s.fontSize]
  const shadow = s.textShadow ? '1px 1px 3px rgba(0,0,0,0.9)' : undefined

  const chatBg: React.CSSProperties =
    s.messageBg === 'dark'
      ? { background: 'rgba(0,0,0,0.60)', padding: '3px 8px', borderRadius: '4px' }
      : s.messageBg === 'rounded'
        ? { background: 'rgba(0,0,0,0.75)', padding: '4px 10px', borderRadius: '6px' }
        : { padding: '1px 0' }

  // Shared text style — block layout so each message is clearly one unit
  const msgBase: React.CSSProperties = {
    fontFamily: 'Tahoma, Arial, sans-serif',
    fontSize,
    lineHeight: '1.4',
    color: textColor,
  }

  function renderMsg(msg: DemoMsg): React.ReactNode {
    switch (msg.type) {
      case 'chat':
        return (
          <div
            style={{
              ...msgBase,
              ...chatBg,
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <ChatBadges msg={msg} hidden={s.hideBadges} />
            <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
            <span style={{ opacity: 0.55 }}>:{' '}</span>
            <span style={{ textShadow: shadow }}>{msg.text}</span>
          </div>
        )
      case 'reply':
        return (
          <div style={{ ...msgBase, ...chatBg }}>
            <div style={{ fontSize: '0.78em', opacity: 0.4, marginBottom: 2 }}>
              ↩ @{msg.replyTo}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
              <ChatBadges msg={msg} hidden={s.hideBadges} />
              <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
              <span style={{ opacity: 0.55 }}>:{' '}</span>
              <span style={{ textShadow: shadow }}>{msg.text}</span>
            </div>
          </div>
        )
      case 'sub':
        return (
          <div
            style={{
              ...msgBase,
              background: 'rgba(145,71,255,0.22)',
              padding: '3px 8px',
              borderRadius: '4px',
              borderLeft: '3px solid rgba(145,71,255,0.65)',
              color: '#ddc8ff',
            }}
          >
            <span style={{ marginRight: 4 }}>⭐</span>
            <span style={{ fontWeight: 700, color: '#c678dd' }}>{msg.username}</span>
            {' 訂閱了！'}
            <span style={{ opacity: 0.5, fontSize: '0.82em' }}> ({msg.detail})</span>
          </div>
        )
      case 'resub':
        return (
          <div
            style={{
              ...msgBase,
              background: 'rgba(145,71,255,0.15)',
              padding: '3px 8px',
              borderRadius: '4px',
              borderLeft: '3px solid rgba(145,71,255,0.45)',
              color: '#ddc8ff',
            }}
          >
            <span style={{ marginRight: 4 }}>🔄</span>
            <span style={{ fontWeight: 700, color: '#c678dd' }}>{msg.username}</span>
            {' 連續訂閱 '}
            <span style={{ fontWeight: 700 }}>{msg.detail}</span>
            {'！'}
          </div>
        )
      case 'gift-sub':
        return (
          <div
            style={{
              ...msgBase,
              background: 'rgba(229,192,123,0.18)',
              padding: '3px 8px',
              borderRadius: '4px',
              borderLeft: '3px solid rgba(229,192,123,0.65)',
              color: '#f0d080',
            }}
          >
            <span style={{ marginRight: 4 }}>🎁</span>
            <span style={{ fontWeight: 700, color: '#e5c07b' }}>{msg.username}</span>
            {' 贈送了 '}
            <span style={{ fontWeight: 700 }}>{msg.detail}</span>
            {' 個訂閱！'}
          </div>
        )
      case 'redemption':
        return (
          <div
            style={{
              ...msgBase,
              ...chatBg,
              background: 'rgba(255,184,0,0.12)',
              borderLeft: '3px solid rgba(255,184,0,0.55)',
            }}
          >
            <span
              style={{
                fontSize: '0.78em',
                fontWeight: 600,
                background: 'rgba(255,184,0,0.28)',
                color: '#ffd700',
                padding: '0 4px',
                borderRadius: 2,
                marginRight: 5,
              }}
            >
              {msg.detail}
            </span>
            <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
            <span style={{ opacity: 0.55 }}>:{' '}</span>
            <span style={{ textShadow: shadow }}>{msg.text}</span>
          </div>
        )
      case 'raid':
        return (
          <div
            style={{
              ...msgBase,
              background: 'rgba(255,107,107,0.18)',
              padding: '3px 8px',
              borderRadius: '4px',
              borderLeft: '3px solid rgba(255,107,107,0.65)',
              color: '#ffcccc',
              textAlign: 'center',
            }}
          >
            <span style={{ marginRight: 4 }}>🚀</span>
            <span style={{ fontWeight: 700, color: '#ff8080' }}>{msg.username}</span>
            {' 帶著 '}
            <span style={{ fontWeight: 700 }}>{msg.detail}</span>
            {' 人突襲！'}
          </div>
        )
      default:
        return null
    }
  }

  const visible = SEQUENCE.filter(m => visibleIds.has(m.id)).slice(-10)

  return (
    <div
      style={{
        background: 'rgba(10,10,20,0.9)',
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        alignItems: s.align === 'right' ? 'flex-end' : 'flex-start',
        padding: '10px',
        boxSizing: 'border-box',
        gap: { compact: '2px', normal: '4px', loose: '8px' }[s.spacing],
        overflow: 'hidden',
      }}
    >
      {visible.map(msg => (
        <motion.div
          key={`${msg.id}-${loopKey}`}
          initial={s.animation ? { opacity: 0, x: s.animDir === 'left' ? -10 : 10 } : false}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          style={{ flexShrink: 0, maxWidth: '100%' }}
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
    <pre className="text-xs leading-relaxed whitespace-pre">
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
            className={`rounded-md border text-sm font-medium transition-colors ${
              opt.desc ? 'flex flex-col px-4 py-2 text-left' : 'px-3 py-1.5'
            } ${
              value === opt.value ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-accent'
            }`}
          >
            {opt.desc ? (
              <>
                <span className="font-medium">{opt.label}</span>
                <span className="text-muted-foreground text-xs">{opt.desc}</span>
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

// ---- Page ----

const BG_OPTIONS: { value: BgOption; label: string; desc: string }[] = [
  { value: 'transparent', label: '透明', desc: '無背景' },
  { value: 'dark', label: '深色', desc: '半透明黑底' },
  { value: 'light', label: '淺色', desc: '半透明白底' },
]

const FONT_SIZE_OPTIONS: { value: FontSizeOption; label: string }[] = [
  { value: 'small', label: '小 13px' },
  { value: 'medium', label: '中 15px' },
  { value: 'large', label: '大 18px' },
]

const SPACING_OPTIONS: { value: SpacingOption; label: string }[] = [
  { value: 'compact', label: '緊湊' },
  { value: 'normal', label: '標準' },
  { value: 'loose', label: '寬鬆' },
]

const MSG_BG_OPTIONS: { value: MsgBgOption; label: string }[] = [
  { value: 'none', label: '無' },
  { value: 'dark', label: '深色方框' },
  { value: 'rounded', label: '深色圓框' },
]

const ALIGN_OPTIONS: { value: AlignOption; label: string }[] = [
  { value: 'left', label: '靠左' },
  { value: 'right', label: '靠右' },
]

const ANIM_DIR_OPTIONS: { value: AnimDirOption; label: string }[] = [
  { value: 'left', label: '從左滑入' },
  { value: 'right', label: '從右滑入' },
]

export default function ChatOverlayModule() {
  useDocumentTitle('Chat Overlay')

  const { user } = useAuth()
  const [settings, setSettings] = useState<ChatCssSettings>(loadSettings)
  const [rightPanel, setRightPanel] = useState<'preview' | 'css'>('preview')

  const patch = (partial: Partial<ChatCssSettings>) =>
    setSettings(prev => ({ ...prev, ...partial }))

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  }, [settings])

  const css = generateCss(settings)

  const copyCss = () => {
    navigator.clipboard.writeText(css).then(
      () => toast.success('CSS 已複製'),
      () => toast.error('複製失敗，請手動選取')
    )
  }

  const twitchUrl = user?.name ? `https://www.twitch.tv/popout/${user.name}/chat?popout=` : ''

  return (
    <PageMain>
      <SlideUpSm inView className="shrink-0">
        <h1 className="text-page-title font-bold">Chat Overlay</h1>
        <p className="text-sub text-muted-foreground mt-0.5">
          自訂 Twitch 聊天室樣式，貼入 OBS Browser Source
        </p>
      </SlideUpSm>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-12 gap-section items-start"
      >
        {/* Left: switchable Preview / CSS */}
        <div className="lg:col-span-6 flex flex-col gap-element h-105 min-w-0 overflow-hidden">
          {/* Tab bar */}
          <div className="flex shrink-0 items-center justify-between">
            <div className="flex gap-1 rounded-lg border p-1">
              {(['preview', 'css'] as const).map(panel => (
                <button
                  key={panel}
                  type="button"
                  onClick={() => setRightPanel(panel)}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    rightPanel === panel
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon
                    icon={panel === 'preview' ? 'fa-solid fa-eye' : 'fa-solid fa-code'}
                    className="text-xs"
                  />
                  {panel === 'preview' ? '預覽' : 'CSS'}
                </button>
              ))}
            </div>
            {rightPanel === 'css' && (
              <Button onClick={copyCss} size="sm">
                <Icon icon="fa-regular fa-copy" className="mr-1.5 text-xs" />
                複製 CSS
              </Button>
            )}
          </div>

          {/* Panel content */}
          {rightPanel === 'preview' ? (
            <>
              <div className="flex-1 min-h-0 overflow-hidden rounded-lg border">
                <ChatPreview s={settings} />
              </div>
              {twitchUrl && <OverlayUrlBlock url={twitchUrl} />}
            </>
          ) : (
            <div className="flex-1 min-h-0 overflow-auto rounded-lg border bg-muted p-4">
              <CssHighlight code={css} />
            </div>
          )}
        </div>

        {/* Right: Settings */}
        <div className="lg:col-span-6 flex flex-col gap-section">
          <Card>
            <CardHeader>
              <CardTitle>樣式設定</CardTitle>
              <CardDescription>調整後自動產生 CSS，無需儲存</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* 背景 */}
              <OptionButtonGroup
                label="背景"
                options={BG_OPTIONS}
                value={settings.background}
                onChange={v => patch({ background: v })}
              />

              {/* 字型大小 + 訊息間距 */}
              <div className="grid grid-cols-2 gap-section">
                <OptionButtonGroup
                  label="字型大小"
                  options={FONT_SIZE_OPTIONS}
                  value={settings.fontSize}
                  onChange={v => patch({ fontSize: v })}
                />
                <OptionButtonGroup
                  label="訊息間距"
                  options={SPACING_OPTIONS}
                  value={settings.spacing}
                  onChange={v => patch({ spacing: v })}
                />
              </div>

              {/* 訊息背景 + 對齊 */}
              <div className="grid grid-cols-2 gap-section">
                <OptionButtonGroup
                  label="訊息背景"
                  options={MSG_BG_OPTIONS}
                  value={settings.messageBg}
                  onChange={v => patch({ messageBg: v })}
                />
                <OptionButtonGroup
                  label="訊息對齊"
                  options={ALIGN_OPTIONS}
                  value={settings.align}
                  onChange={v => patch({ align: v })}
                />
              </div>

              {/* 隱藏元素 */}
              <div className="flex flex-col gap-2">
                <p className="text-label font-medium text-muted-foreground">隱藏元素</p>
                <div className="flex flex-col gap-element">
                  {(
                    [
                      { key: 'hideHeader', label: '標題列', desc: '移除聊天室頂部標題' },
                      { key: 'hideInput', label: '輸入框', desc: '移除底部聊天輸入區' },
                      { key: 'hideTimestamp', label: '時間戳記', desc: '移除訊息旁的時間顯示' },
                      { key: 'hideBadges', label: '徽章', desc: 'MOD、VIP、訂閱者圖標' },
                    ] as const
                  ).map(({ key, label, desc }) => (
                    <div key={key} className="flex items-center justify-between">
                      <div>
                        <Label htmlFor={key}>{label}</Label>
                        <p className="text-muted-foreground mt-0.5 text-label">{desc}</p>
                      </div>
                      <Switch
                        id={key}
                        checked={settings[key]}
                        onCheckedChange={v => patch({ [key]: v })}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* 視覺效果 */}
              <div className="flex flex-col gap-2">
                <p className="text-label font-medium text-muted-foreground">視覺效果</p>
                <div className="flex flex-col gap-element">
                  {(
                    [
                      { key: 'textShadow', label: '文字陰影', desc: '透明背景時提高可讀性' },
                      { key: 'animation', label: '進場動畫', desc: '新訊息滑入淡出效果' },
                    ] as const
                  ).map(({ key, label, desc }) => (
                    <div key={key} className="flex items-center justify-between">
                      <div>
                        <Label htmlFor={key}>{label}</Label>
                        <p className="text-muted-foreground mt-0.5 text-label">{desc}</p>
                      </div>
                      <Switch
                        id={key}
                        checked={settings[key]}
                        onCheckedChange={v => patch({ [key]: v })}
                      />
                    </div>
                  ))}
                  {settings.animation && (
                    <OptionButtonGroup
                      label="滑入方向"
                      options={ANIM_DIR_OPTIONS}
                      value={settings.animDir}
                      onChange={v => patch({ animDir: v })}
                      className="pl-1"
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
