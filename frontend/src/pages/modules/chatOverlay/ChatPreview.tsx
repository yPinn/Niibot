import React, { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'

import { type BadgeEntry, TwitchBadgeGroup } from '@/components/primitives'

import { type BadgeFilterOption, type ChatCssSettings } from '../chatOverlayCss'

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

export function ChatPreview({ s }: { s: ChatCssSettings }) {
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
