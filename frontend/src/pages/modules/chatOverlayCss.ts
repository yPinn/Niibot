import { BOT_USERNAME } from '../../api/config'

// ---- Types ----

export type BgOption = 'transparent' | 'color'
export type FontSizeOption = number
export type SpacingOption = 'compact' | 'normal' | 'loose'
export type MsgBgOption = 'none' | 'dark' | 'rounded' | 'bubble'
export type AlignOption = 'left' | 'right'
export type AnimDirOption = 'left' | 'right'
export type BadgeFilterOption = 'all' | 'role-sub' | 'none'

export interface ChatCssSettings {
  background: BgOption
  bgColor: string
  fontSize: FontSizeOption
  spacing: SpacingOption
  messageBg: MsgBgOption
  align: AlignOption
  hideHeader: boolean
  badgeFilter: BadgeFilterOption
  textShadow: boolean
  animation: boolean
  animDir: AnimDirOption
  hideBot: boolean
}

export const DEFAULT_SETTINGS: ChatCssSettings = {
  background: 'transparent',
  bgColor: '#0e0e0e',
  fontSize: 14,
  spacing: 'normal',
  messageBg: 'bubble',
  align: 'left',
  hideHeader: true,
  badgeFilter: 'role-sub',
  textShadow: false,
  animation: true,
  animDir: 'left',
  hideBot: false,
}

const STORAGE_KEY = 'niibot:chat-overlay-css'

export function saveSettings(s: ChatCssSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}

export function loadSettings(): ChatCssSettings {
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
      // Migrate old hideBadges boolean → badgeFilter
      if (parsed.hideBadges === true) parsed.badgeFilter = 'none'
      else if (parsed.hideBadges === false) parsed.badgeFilter = 'all'
      delete parsed.hideBadges
      return { ...DEFAULT_SETTINGS, ...parsed }
    }
  } catch {
    // ignore JSON parse errors — fall back to defaults
  }
  return DEFAULT_SETTINGS
}

// ---- CSS Generator ----
//
// Targets only semantic class names and data-* attributes — never styled-components
// hash classes (e.g. Layout-sc-*, gyMdFQ) which change on every Twitch deployment.

export function generateCss(s: ChatCssSettings): string {
  const parts: string[] = []

  parts.push('/* Twitch Chat Override — paste into OBS Browser Source > Custom CSS */')

  const bg = s.background === 'color' ? s.bgColor : 'transparent'

  // Set body background; always clear inner containers so body colour shows through.
  // Semantic targets that survive Twitch deployments — styled-components hashes are excluded.
  parts.push(
    `body {\n  background-color: ${bg} !important;\n  overflow: hidden !important;\n}\n\n.stream-chat,\n.chat-room,\n.chat-room__content,\n.chat-list--default,\n.scrollable-container,\n.scrollable-contents,\nseventv-container {\n  background-color: transparent !important;\n}`
  )

  // Hide all scrollbars — OBS uses Chromium (CEF) so ::-webkit-scrollbar is the main target
  parts.push(
    `::-webkit-scrollbar {\n  display: none !important;\n}\n\n* {\n  scrollbar-width: none !important;\n}`
  )

  // Always suppress noise elements in an OBS overlay context
  parts.push(
    `.chat-line__status,\n.chat-line__message-highlight,\n[class*="leaderboard"],\n.community-highlight-stack,\n.community-highlight-stack__card,\n.new-chatter-ritual,\n.consent-banner,\n.paid-pinned-chat-message-list,\n.paid-pinned-chat-message-content-wrapper,\n.chat-author__intl-login,\n[class*="hype-train"],\n[class*="predictions"],\nbutton[aria-label*="reply"],\nbutton[aria-label*="返信"] {\n  display: none !important;\n}`
  )

  if (s.hideHeader) {
    parts.push(`.stream-chat-header,\ndiv.rooms-header {\n  display: none !important;\n}`)
  }

  // Input is always hidden — this overlay is display-only
  parts.push(`.chat-input {\n  display: none !important;\n}`)

  if (s.badgeFilter === 'none') {
    parts.push(`.chat-badge,\n.seventv-badge {\n  display: none !important;\n}`)
  } else if (s.badgeFilter === 'role-sub') {
    // Hide all badges first, then reveal role badges and subscriber badges.
    // Uses both zh-TW and en alt text so the rule works regardless of Twitch locale.
    parts.push(
      `.chat-badge,\n.seventv-badge {\n  display: none !important;\n}\n\n.chat-badge[alt="直播主"],\n.chat-badge[alt="Broadcaster"],\n.chat-badge[alt="版主"],\n.chat-badge[alt="Moderator"],\n.chat-badge[alt="VIP"],\n.chat-badge[alt*="Prime"],\n.chat-badge[alt*="訂閱"],\n.chat-badge[alt*="Subscriber"],\n.chat-badge[alt*="subscriber"] {\n  display: inline !important;\n}`
    )
  }

  const fontSize = `${s.fontSize}px`
  const marginY = { compact: '2px', normal: '4px', loose: '8px' }[s.spacing]

  if (s.messageBg === 'bubble') {
    const bubbleRadius = s.align === 'right' ? '14px 3px 14px 14px' : '3px 14px 14px 14px'
    const marginAuto = s.align === 'right' ? 'margin-left: auto' : 'margin-right: auto'
    // Use margin-left/right: auto for alignment — align-items on the outer flex wrapper breaks
    // when bubble content wraps (inner block container expands to full width, defeating flex).
    parts.push(
      `.chat-line__message {\n  font-size: ${fontSize} !important;\n  background: transparent !important;\n  padding: 0 6px !important;\n  margin: ${marginY} 0 !important;\n}`
    )
    const alignSelf = s.align === 'right' ? 'flex-end' : 'flex-start'
    parts.push(
      `.chat-line__username-container {\n  display: flex !important;\n  align-items: center !important;\n  flex-wrap: nowrap !important;\n  overflow: hidden !important;\n  font-size: 0.78em !important;\n  max-width: 90% !important;\n  width: fit-content !important;\n  align-self: ${alignSelf} !important;\n  ${marginAuto} !important;\n  margin-bottom: 3px !important;\n}`
    )
    // Badge wrapper is the first <span> child; make it inline-flex so InjectLayout divs
    // (each wrapping one badge button) are placed in a proper row instead of absolute-stacking.
    // The > div rule resets any position:absolute that InjectLayout applies by default.
    parts.push(
      `.chat-line__username-container > span:first-child {\n  display: inline-flex !important;\n  align-items: center !important;\n  gap: 2px !important;\n  flex-shrink: 0 !important;\n}\n\n.chat-line__username-container > span:first-child > div {\n  position: relative !important;\n}\n\n.chat-line__username {\n  margin-left: 4px !important;\n}`
    )
    // Username floats on background — always add shadow for legibility.
    // Strip 7TV gradient paint (background-clip: text + color:transparent) so the
    // Twitch per-user inline color is restored; [data-a-user] is a stable Twitch fallback.
    parts.push(
      `.chat-author__display-name,\n.chat-line__username [data-a-user] {\n  background: none !important;\n  -webkit-background-clip: unset !important;\n  background-clip: unset !important;\n  -webkit-text-fill-color: unset !important;\n  white-space: nowrap !important;\n  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85), 0 1px 6px rgba(0, 0, 0, 0.6) !important;\n}`
    )
    // Hide the colon separator — aria-hidden span is Twitch's stable marker for it.
    parts.push(`.chat-line__message span[aria-hidden="true"] {\n  display: none !important;\n}`)
    // Bubble: always dark bg + white text regardless of body background.
    // seventv-chat-message covers lines rendered by the 7TV extension.
    // margin-auto on display:block + max-width ensures alignment holds even when text wraps.
    const marginAutoReset = s.align === 'right' ? 'margin-right: 0' : 'margin-left: 0'
    parts.push(
      `[data-a-target="chat-line-message-body"],\n[data-test-selector="chat-line-message-body"],\nseventv-chat-message {\n  font-size: ${fontSize} !important;\n  line-height: 1.5 !important;\n  background: rgba(0, 0, 0, 0.68) !important;\n  border-radius: ${bubbleRadius} !important;\n  padding: 8px 14px !important;\n  max-width: 90% !important;\n  width: fit-content !important;\n  word-break: break-word !important;\n  align-self: ${alignSelf} !important;\n  ${marginAuto} !important;\n  ${marginAutoReset} !important;\n  color: #fff !important;\n  display: block !important;\n}`
    )
    // Emotes inside bubbles must stay inline so they pack with text instead of wrapping as blocks
    parts.push(
      `[data-a-target="chat-line-message-body"] img,\n[data-test-selector="chat-line-message-body"] img,\nseventv-chat-message img {\n  display: inline-block !important;\n  vertical-align: middle !important;\n}`
    )
    // Broadcaster messages appear on the opposite side — flip margins and align-self for both username and body.
    const bcRadius = s.align === 'right' ? '3px 14px 14px 14px' : '14px 3px 14px 14px'
    const bcMarginAuto = s.align === 'right' ? 'margin-right: auto' : 'margin-left: auto'
    const bcMarginReset = s.align === 'right' ? 'margin-left: 0' : 'margin-right: 0'
    const bcAlignSelf = s.align === 'right' ? 'flex-start' : 'flex-end'
    parts.push(
      `.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) .chat-line__username-container,\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) [data-a-target="chat-line-message-body"],\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) [data-test-selector="chat-line-message-body"],\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) seventv-chat-message {\n  ${bcMarginAuto} !important;\n  ${bcMarginReset} !important;\n  align-self: ${bcAlignSelf} !important;\n}\n\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) [data-a-target="chat-line-message-body"],\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) [data-test-selector="chat-line-message-body"],\n.chat-line__message:has(.chat-badge[alt="Broadcaster"], .chat-badge[alt="直播主"]) seventv-chat-message {\n  border-radius: ${bcRadius} !important;\n}`
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
    // Strip 7TV gradient paint so Twitch inline username color is restored
    parts.push(
      `.chat-author__display-name,\n.chat-line__username [data-a-user] {\n  background: none !important;\n  -webkit-background-clip: unset !important;\n  background-clip: unset !important;\n  -webkit-text-fill-color: unset !important;\n}`
    )
  }

  if (s.textShadow) {
    parts.push(`span.text-fragment {\n  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.9) !important;\n}`)
  }

  if (s.align === 'right') {
    const textAlignRule =
      s.messageBg !== 'bubble'
        ? '\n\n.chat-line__message {\n  text-align: right !important;\n}'
        : ''
    parts.push(
      `.chat-list--default,\n.chat-scrollable-area__message-container,\n.scrollable-contents {\n  align-items: flex-end !important;\n}${textAlignRule}`
    )
  }

  if (s.animation) {
    const fromX = s.animDir === 'left' ? '-10px' : '10px'
    parts.push(
      `@keyframes niiChatIn {\n  from { opacity: 0; transform: translateX(${fromX}); }\n  to   { opacity: 1; transform: translateX(0); }\n}\n\n.chat-line__message {\n  animation: niiChatIn 0.2s ease-out !important;\n}`
    )
  }

  if (s.hideBot) {
    // Badge-based: covers standard Twitch verified bots (en + zh-TW)
    parts.push(
      `.chat-line__message:has(.chat-badge[alt="Verified Bot"]),\n.chat-line__message:has(.chat-badge[alt="Bot"]),\n.chat-line__message:has(.chat-badge[alt="已驗證機器人"]),\n.chat-line__message:has(.chat-badge[alt="機器人"]) {\n  display: none !important;\n}`
    )
    // Username-based fallback: BOT_USERNAME comes from VITE_BOT_USERNAME env var.
    if (BOT_USERNAME) {
      parts.push(
        `.chat-line__message[data-a-user="${BOT_USERNAME}"] {\n  display: none !important;\n}`
      )
    }
  }

  return parts.join('\n\n')
}
