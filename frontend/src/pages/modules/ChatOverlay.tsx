import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { toast } from 'sonner'

import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { PageMain } from '@/components/PageMain'
import {
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
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ---- Types ----

type BgOption = 'transparent' | 'dark' | 'light'
type FontSizeOption = 'small' | 'medium' | 'large'
type MsgBgOption = 'none' | 'dark' | 'rounded'

interface ChatCssSettings {
  background: BgOption
  fontSize: FontSizeOption
  messageBg: MsgBgOption
  hideHeader: boolean
  hideInput: boolean
  hideBadges: boolean
  textShadow: boolean
  animation: boolean
}

const DEFAULT_SETTINGS: ChatCssSettings = {
  background: 'transparent',
  fontSize: 'medium',
  messageBg: 'dark',
  hideHeader: true,
  hideInput: true,
  hideBadges: false,
  textShadow: false,
  animation: true,
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
  parts.push('')

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
  const [msgBg, msgPad, msgRadius] =
    s.messageBg === 'dark'
      ? ['rgba(0, 0, 0, 0.60)', '4px 8px', '4px']
      : s.messageBg === 'rounded'
        ? ['rgba(0, 0, 0, 0.75)', '5px 10px', '6px']
        : ['transparent', '2px 4px', '0']

  parts.push(
    `.chat-line__message {\n  font-size: ${fontSize} !important;\n  background: ${msgBg} !important;\n  padding: ${msgPad} !important;\n  border-radius: ${msgRadius} !important;\n  margin: 2px 0 !important;\n}`
  )

  if (s.textShadow) {
    parts.push(
      `.chat-line__message * {\n  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.9) !important;\n}`
    )
  }

  if (s.animation) {
    parts.push(
      `@keyframes niiChatIn {\n  from { opacity: 0; transform: translateY(4px); }\n  to   { opacity: 1; transform: translateY(0); }\n}\n\n.chat-line__message {\n  animation: niiChatIn 0.15s ease-out !important;\n}`
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
  }, [s.background, s.fontSize, s.messageBg, s.hideBadges, s.textShadow, s.animation])

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

  function badges(msg: DemoMsg) {
    if (s.hideBadges) return null
    const items: React.ReactNode[] = []
    if (msg.is_mod)
      items.push(
        <img
          key="mod"
          src="/twitch-badges/moderator/1x.png"
          alt="mod"
          width={18}
          height={18}
          style={{ marginRight: 3, verticalAlign: 'middle' }}
          draggable={false}
        />
      )
    if (msg.is_vip)
      items.push(
        <img
          key="vip"
          src="/twitch-badges/vip/1x.png"
          alt="vip"
          width={18}
          height={18}
          style={{ marginRight: 3, verticalAlign: 'middle' }}
          draggable={false}
        />
      )
    if (msg.is_sub && !msg.is_mod && !msg.is_vip)
      items.push(
        <img
          key="sub"
          src="/twitch-badges/subscriber/1x.png"
          alt="sub"
          width={18}
          height={18}
          style={{ marginRight: 3, verticalAlign: 'middle' }}
          draggable={false}
        />
      )
    return items.length > 0 ? <>{items}</> : null
  }

  function renderMsg(msg: DemoMsg): React.ReactNode {
    switch (msg.type) {
      case 'chat':
        return (
          <div style={{ ...msgBase, ...chatBg }}>
            {badges(msg)}
            <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
            <span style={{ opacity: 0.55 }}>: </span>
            <span style={{ textShadow: shadow }}>{msg.text}</span>
          </div>
        )
      case 'reply':
        return (
          <div style={{ ...msgBase, ...chatBg }}>
            <div style={{ fontSize: '0.78em', opacity: 0.4, marginBottom: 2 }}>
              ↩ @{msg.replyTo}
            </div>
            <div>
              {badges(msg)}
              <span style={{ fontWeight: 700, color: msg.color }}>{msg.username}</span>
              <span style={{ opacity: 0.55 }}>: </span>
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
            <span style={{ opacity: 0.55 }}>: </span>
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
        padding: '10px',
        boxSizing: 'border-box',
        gap: '4px',
        overflow: 'hidden',
      }}
    >
      {visible.map(msg => (
        <motion.div
          key={`${msg.id}-${loopKey}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          style={{ flexShrink: 0 }}
        >
          {renderMsg(msg)}
        </motion.div>
      ))}
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

const MSG_BG_OPTIONS: { value: MsgBgOption; label: string }[] = [
  { value: 'none', label: '無' },
  { value: 'dark', label: '深色方框' },
  { value: 'rounded', label: '深色圓框' },
]

export default function ChatOverlayModule() {
  useDocumentTitle('Chat Overlay')

  const { user } = useAuth()
  const [settings, setSettings] = useState<ChatCssSettings>(loadSettings)

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
    <PageMain className="h-full overflow-hidden">
      <SlideUpSm inView className="flex items-end justify-between gap-element shrink-0">
        <div>
          <h1 className="text-page-title font-bold">Chat Overlay</h1>
          <p className="text-sub text-muted-foreground mt-0.5">
            自訂 Twitch 聊天室樣式，貼入 OBS Browser Source
          </p>
        </div>
        <Button onClick={copyCss} size="sm">
          <Icon icon="fa-regular fa-copy" className="mr-1.5 text-xs" />
          複製 CSS
        </Button>
      </SlideUpSm>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-12 gap-section flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid-rows-1"
      >
        {/* Settings + CSS output */}
        <div className="lg:col-span-7 flex flex-col gap-section lg:overflow-y-auto">
          <Card>
            <CardHeader>
              <CardTitle>樣式設定</CardTitle>
              <CardDescription>調整後自動產生 CSS，無需儲存</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* Background */}
              <div className="flex flex-col gap-2">
                <Label>背景</Label>
                <div className="flex flex-wrap gap-2">
                  {BG_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => patch({ background: opt.value })}
                      className={`flex flex-col rounded-md border px-4 py-2 text-left transition-colors ${
                        settings.background === opt.value
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-accent'
                      }`}
                    >
                      <span className="text-sm font-medium">{opt.label}</span>
                      <span className="text-muted-foreground text-xs">{opt.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Font size */}
              <div className="flex flex-col gap-2">
                <Label>字型大小</Label>
                <div className="flex flex-wrap gap-2">
                  {FONT_SIZE_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => patch({ fontSize: opt.value })}
                      className={`rounded-md border px-4 py-1.5 text-sm font-medium transition-colors ${
                        settings.fontSize === opt.value
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-accent'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Message background */}
              <div className="flex flex-col gap-2">
                <Label>訊息背景</Label>
                <div className="flex flex-wrap gap-2">
                  {MSG_BG_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => patch({ messageBg: opt.value })}
                      className={`rounded-md border px-4 py-1.5 text-sm font-medium transition-colors ${
                        settings.messageBg === opt.value
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'hover:bg-accent'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Toggles */}
              <div className="flex flex-col gap-4">
                {(
                  [
                    { key: 'hideHeader', label: '隱藏標題列', desc: '移除聊天室頂部標題' },
                    { key: 'hideInput', label: '隱藏輸入框', desc: '移除底部聊天輸入區' },
                    { key: 'hideBadges', label: '隱藏徽章', desc: 'MOD、訂閱者圖標' },
                    { key: 'textShadow', label: '文字陰影', desc: '透明背景時提高可讀性' },
                    { key: 'animation', label: '進場動畫', desc: '新訊息淡入滑入效果' },
                  ] as const
                ).map(({ key, label, desc }) => (
                  <div key={key} className="flex items-center justify-between">
                    <div>
                      <Label htmlFor={key}>{label}</Label>
                      <p className="text-muted-foreground mt-0.5 text-xs">{desc}</p>
                    </div>
                    <Switch
                      id={key}
                      checked={settings[key]}
                      onCheckedChange={v => patch({ [key]: v })}
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Generated CSS */}
          <Card>
            <CardHeader>
              <CardTitle>產生的 CSS</CardTitle>
              <CardDescription>複製後貼入 OBS Browser Source → Custom CSS</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <pre className="bg-muted text-muted-foreground max-h-64 overflow-auto rounded-md p-4 text-xs leading-relaxed">
                {css}
              </pre>
            </CardContent>
          </Card>
        </div>

        {/* Preview + URL */}
        <div className="lg:col-span-5 flex flex-col gap-section min-h-0">
          <div className="flex-1 min-h-[200px] max-h-[420px] overflow-hidden rounded-lg border">
            <ChatPreview s={settings} />
          </div>
          {twitchUrl && <OverlayUrlBlock url={twitchUrl} />}
        </div>
      </SlideUp>
    </PageMain>
  )
}
