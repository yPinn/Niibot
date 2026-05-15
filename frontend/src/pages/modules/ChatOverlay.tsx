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

type BgOption = 'transparent' | 'color'
type FontSizeOption = number
type SpacingOption = 'compact' | 'normal' | 'loose'
type MsgBgOption = 'none' | 'dark' | 'rounded' | 'bubble'
type AlignOption = 'left' | 'right'
type AnimDirOption = 'left' | 'right'

interface ChatCssSettings {
  background: BgOption
  bgColor: string
  fontSize: FontSizeOption
  spacing: SpacingOption
  messageBg: MsgBgOption
  align: AlignOption
  hideHeader: boolean
  hideBadges: boolean
  textShadow: boolean
  animation: boolean
  animDir: AnimDirOption
}

const DEFAULT_SETTINGS: ChatCssSettings = {
  background: 'transparent',
  bgColor: '#0e0e0e',
  fontSize: 14,
  spacing: 'normal',
  messageBg: 'bubble',
  align: 'left',
  hideHeader: true,
  hideBadges: false,
  textShadow: false,
  animation: true,
  animDir: 'left',
}

const STORAGE_KEY = 'niibot:chat-overlay-css'

function loadSettings(): ChatCssSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      // Migrate old 'dark'/'light' presets to 'color'
      if (parsed.background === 'dark') {
        parsed.background = 'color'
        parsed.bgColor = '#0e0e0e'
      }
      if (parsed.background === 'light') {
        parsed.background = 'color'
        parsed.bgColor = '#f0f0f0'
      }
      if (parsed.fontSize === 'small') parsed.fontSize = 14
      if (parsed.fontSize === 'medium') parsed.fontSize = 16
      if (parsed.fontSize === 'large') parsed.fontSize = 18
      return { ...DEFAULT_SETTINGS, ...parsed }
    }
  } catch {
    // ignore JSON parse errors — fall back to defaults
  }
  return DEFAULT_SETTINGS
}

// ---- CSS Generator ----

function generateCss(s: ChatCssSettings): string {
  const parts: string[] = []

  parts.push('/* Twitch Chat Override — paste into OBS Browser Source > Custom CSS */')

  const bg = s.background === 'color' ? s.bgColor : 'transparent'

  // Set body background; always clear inner React containers so body colour shows through
  parts.push(
    `body {\n  background-color: ${bg} !important;\n  overflow: hidden !important;\n}\n\ndiv.twilight-minimal-root,\ndiv.popout-chat-page,\nsection.chat-room,\n.stream-chat,\n.chat-room,\n.chat-list,\n.scrollable-area {\n  background-color: transparent !important;\n}`
  )

  // Always suppress noise elements in an OBS overlay context
  parts.push(
    `.chat-line__status,\n[class*="leaderboard"],\n.community-highlight-stack__card,\n.new-chatter-ritual,\n.consent-banner,\n.paid-pinned-chat-message-list,\n.paid-pinned-chat-message-content-wrapper,\n.chat-author__intl-login,\nbutton[aria-label*="reply"],\nbutton[aria-label*="返信"] {\n  display: none !important;\n}`
  )

  if (s.hideHeader) {
    parts.push(`.stream-chat-header,\ndiv.rooms-header {\n  display: none !important;\n}`)
  }

  // Input is always hidden — this overlay is display-only
  parts.push(`.chat-input {\n  display: none !important;\n}`)

  if (s.hideBadges) {
    parts.push(`.chat-badge {\n  display: none !important;\n}`)
  }

  const fontSize = `${s.fontSize}px`
  const marginY = { compact: '2px', normal: '4px', loose: '8px' }[s.spacing]

  if (s.messageBg === 'bubble') {
    const bubbleRadius = s.align === 'right' ? '14px 3px 14px 14px' : '3px 14px 14px 14px'
    parts.push(
      `.chat-line__message {\n  display: flex !important;\n  flex-direction: column !important;\n  align-items: ${s.align === 'right' ? 'flex-end' : 'flex-start'} !important;\n  font-size: ${fontSize} !important;\n  background: transparent !important;\n  padding: 0 !important;\n  margin: ${marginY} 0 !important;\n}`
    )
    parts.push(
      `.chat-line__username-container {\n  display: flex !important;\n  align-items: center !important;\n  font-size: 0.78em !important;\n  margin-bottom: 3px !important;\n}`
    )
    // Username floats on background — always add shadow for legibility
    parts.push(
      `.chat-author__display-name {\n  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85), 0 1px 6px rgba(0, 0, 0, 0.6) !important;\n}`
    )
    // Hide the colon separator between username and message
    parts.push(`.chat-line__username-container > span:last-child {\n  display: none !important;\n}`)
    // Bubble: always dark bg + white text regardless of body background
    parts.push(
      `[data-a-target="chat-line-message-body"],\n[data-test-selector="chat-line-message-body"] {\n  font-size: ${fontSize} !important;\n  line-height: 1.5 !important;\n  background: rgba(0, 0, 0, 0.68) !important;\n  border-radius: ${bubbleRadius} !important;\n  padding: 8px 14px !important;\n  max-width: 85% !important;\n  color: #fff !important;\n  display: block !important;\n}`
    )
    // Broadcaster messages appear on the opposite side
    const bcAlignItems = s.align === 'right' ? 'flex-start' : 'flex-end'
    const bcRadius = s.align === 'right' ? '3px 14px 14px 14px' : '14px 3px 14px 14px'
    parts.push(
      `.chat-line__message:has(.chat-badge[alt="Broadcaster"]) {\n  align-items: ${bcAlignItems} !important;\n}\n.chat-line__message:has(.chat-badge[alt="Broadcaster"]) [data-a-target="chat-line-message-body"],\n.chat-line__message:has(.chat-badge[alt="Broadcaster"]) [data-test-selector="chat-line-message-body"] {\n  border-radius: ${bcRadius} !important;\n}`
    )
  } else {
    const [msgBg, msgPad, msgRadius] =
      s.messageBg === 'dark'
        ? ['rgba(0, 0, 0, 0.52)', '4px 10px', '4px']
        : s.messageBg === 'rounded'
          ? ['rgba(0, 0, 0, 0.62)', '6px 12px', '12px']
          : ['transparent', '2px 0', '0']
    parts.push(
      `.chat-line__message {\n  font-size: ${fontSize} !important;\n  background: ${msgBg} !important;\n  padding: ${msgPad} !important;\n  border-radius: ${msgRadius} !important;\n  margin: ${marginY} 0 !important;\n}`
    )
  }

  if (s.textShadow) {
    parts.push(`span.text-fragment {\n  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.9) !important;\n}`)
  }

  if (s.align === 'right' && s.messageBg !== 'bubble') {
    parts.push(
      `.chat-list,\n.chat-scrollable-area__message-container {\n  align-items: flex-end !important;\n}\n\n.chat-line__message {\n  text-align: right !important;\n}`
    )
  } else if (s.align === 'right' && s.messageBg === 'bubble') {
    parts.push(
      `.chat-list,\n.chat-scrollable-area__message-container {\n  align-items: flex-end !important;\n}`
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

function ChatBadges({ msg, hidden }: { msg: DemoMsg; hidden: boolean }) {
  if (hidden) return null
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
    s.hideBadges,
    s.textShadow,
    s.animation,
    s.animDir,
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

  const chatBg: React.CSSProperties =
    s.messageBg === 'dark'
      ? { background: 'rgba(0,0,0,0.52)', padding: '3px 10px', borderRadius: '4px' }
      : s.messageBg === 'rounded'
        ? { background: 'rgba(0,0,0,0.62)', padding: '5px 12px', borderRadius: '12px' }
        : { padding: '1px 0' }

  const msgBase: React.CSSProperties = {
    fontFamily: 'Tahoma, Arial, sans-serif',
    fontSize,
    lineHeight: '1.5',
    color: textColor,
    wordBreak: 'break-word',
    overflowWrap: 'break-word',
  }

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
              gap: 3,
              fontSize: '0.78em',
              marginBottom: 3,
            }}
          >
            <ChatBadges msg={msg} hidden={s.hideBadges} />
            <span style={{ fontWeight: 700, color: msg.color, textShadow: usernameShadow }}>
              {msg.username}
            </span>
          </div>
          {/* Bubble always has dark bg — message text is always white */}
          <div
            style={{
              background: 'rgba(0,0,0,0.68)',
              borderRadius: bubbleRadius,
              padding: '8px 14px',
              maxWidth: '85%',
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
                <ChatBadges msg={msg} hidden={s.hideBadges} />
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
            <ChatBadges msg={msg} hidden={s.hideBadges} />
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

export default function ChatOverlayModule() {
  useDocumentTitle('Chat Overlay')

  const { user } = useAuth()
  const [settings, setSettings] = useState<ChatCssSettings>(loadSettings)
  const [rightPanel, setRightPanel] = useState<'preview' | 'css'>('preview')

  const patch = (partial: Partial<ChatCssSettings>) =>
    setSettings(prev => {
      const next = { ...prev, ...partial }
      // text shadow only applies to transparent backgrounds — reset when leaving transparent
      if (partial.background && partial.background !== 'transparent') next.textShadow = false
      return next
    })

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

  const twitchUrl = user?.name ? `https://www.twitch.tv/popout/${user.name}/chat` : ''

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
        <div className="lg:col-span-6 flex flex-col gap-element min-w-0">
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
              {/* 9:16 mobile aspect ratio preview */}
              <div className="flex justify-center">
                <div
                  className="overflow-hidden rounded-lg border w-full max-w-[260px]"
                  style={{ aspectRatio: '9/16' }}
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
            <CardHeader>
              <CardTitle>樣式設定</CardTitle>
              <CardDescription>調整後自動產生 CSS，無需儲存</CardDescription>
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
                        className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                          settings.background === opt
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'hover:bg-accent'
                        }`}
                      >
                        {opt === 'transparent' ? '透明' : '顏色'}
                      </button>
                    ))}
                    {settings.background === 'color' && (
                      <label className="cursor-pointer" title="選擇背景顏色">
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
                  {(
                    [
                      { key: 'hideHeader', label: '隱藏標題列', desc: undefined },
                      { key: 'hideBadges', label: '隱藏徽章', desc: 'MOD、VIP、訂閱者' },
                    ] as { key: 'hideHeader' | 'hideBadges'; label: string; desc?: string }[]
                  ).map(({ key, label, desc }) => (
                    <div key={key} className="flex items-center justify-between">
                      <div>
                        <Label htmlFor={key}>{label}</Label>
                        {desc && <p className="text-muted-foreground mt-0.5 text-label">{desc}</p>}
                      </div>
                      <Switch
                        id={key}
                        checked={settings[key]}
                        onCheckedChange={v => patch({ [key]: v })}
                      />
                    </div>
                  ))}
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
