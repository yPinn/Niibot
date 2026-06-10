/**
 * Valorant crosshair profile code decoder
 * Verified against: in-game TC UI screenshots + genesy/crosshair-codes source
 *
 * Code structure:  0;[s;1;][c;1;][p;0;]P;{primary kv};[A;{ADS kv};][S;{sniper kv}]
 *   0     = format version
 *   s;1   = advanced options enabled (ADS separate from primary)
 *   c;1   = overrideAllPrimaryCrosshair (apply primary to all weapons) — UI-only
 *   p;0   = ADS does NOT copy primary
 *   P;  = Primary crosshair section start
 *   A;  = ADS (開鏡瞄準模式) section — only present when s;1 + p;0
 *   S;  = Sniper (狙擊鏡) section — uses completely different keys, parsed separately
 *
 * ─── Primary section key reference ─────────────────────────────────────────
 *
 *  COLOR
 *   c   color index  0=白 1=綠 2=黃綠 3=綠黃 4=黃 5=青 6=粉紅 7=紅 8=自訂
 *   u   custom hex   RRGGBB or RRGGBBFF  (only when c=8)
 *
 *  OUTLINE (外框)                                          default
 *   h   outlines enabled    bool (h;0 = off)              true
 *   t   outline thickness   int  0-6                      1
 *   o   outline opacity     float 0-1                     0.5
 *
 *  CENTER DOT (準星中心點) — rendered as a square in-game  default
 *   d   center dot          bool (d;1 = on)               false
 *   z   dot thickness       int  1-6                      2
 *   a   dot opacity         float 0-1                     1
 *
 *  BEHAVIOR / MISC                                         default
 *   b   custom-color marker  required alongside c=8+u     — not rendered
 *   f   fadeTopLinesWhenSpraying  bool (f;1 = on)         false  — not in static preview
 *   s   showSpectatorsCrosshair   bool (s;0 = off)        true   — not in static preview
 *   m   override firing error offset with crosshair offset bool  false
 *       將十字準星偏移套用至射擊誤差偏移
 *       When true: FIXED_GAP is NOT added; raw offset = visual gap
 *       When false + firing error on: visual gap = offset + FIXED_GAP(4)
 *
 *  INNER LINES (內側線) — prefix "0"                       default
 *   0b  show inner lines    bool (0b;0 = hidden)          true
 *   0a  opacity             float 0-1                     0.8
 *   0g  length not linked   bool (0g;1 = 解除綁定)        false
 *   0l  horizontal length   int  0-20                     6
 *   0v  vertical length     int  0-20  (only when 0g=1)   = 0l
 *   0t  thickness           int  0-10                     2
 *   0o  offset from center  int  0-20                     3
 *   0f  firing error        bool (0f;0 = off)             true   射擊誤差
 *   0e  firing error mult   float 0-3                     1
 *   0m  movement error      bool (0m;1 = on)              false  移動失誤
 *   0s  movement error mult float 0-3                     1
 *
 *  OUTER LINES (外側線) — prefix "1"  (same keys, different defaults)
 *   1b  show outer lines    bool (1b;0 = hidden)          true
 *   1a  opacity             float 0-1                     0.35
 *   1g  length not linked   bool                          false
 *   1l  horizontal length   int  0-20                     2
 *   1v  vertical length     int  0-20  (only when 1g=1)   = 1l
 *   1t  thickness           int  0-10                     2
 *   1o  offset from center  int  0-20                     10
 *   1f  firing error        bool (1f;0 = off)             true
 *   1e  firing error mult   float 0-3                     1
 *   1m  movement error      bool (1m;0 = off)             true   ← default ON
 *   1s  movement error mult float 0-3                     1
 *
 * ─── Sniper section (S;) key reference ────────────────────────────────────
 *  Only center-dot settings; no lines.
 *   c   color index  (same palette as primary, default 7 = red)
 *   u   custom hex   RRGGBB (only when c=8)
 *   d   center dot   bool — default TRUE for sniper (absent = on, "d;0" = off)
 *   a   dot opacity  float 0-1   default 0.75
 *   z   dot thickness int  1-6   default 1
 *
 * ─── Visual gap calculation (static preview) ────────────────────────────────
 *   visual_gap = offset   (raw param, no FIXED_GAP adjustment needed for static render)
 *   FIXED_GAP (4 units) is a firing-spread constant, not a static position offset.
 */

export interface ValorantCrosshairParams {
  // Color
  color: string

  // Outline (外框)
  outlines: boolean // h
  outlineThickness: number // t  (0-6)
  outlineOpacity: number // o  (0-1)

  // Inner lines (內側線)
  showInnerLines: boolean // 0b
  innerOpacity: number // 0a  (0-1)
  innerLengthNotLinked: boolean // 0g  解除綁定
  innerLength: number // 0l  horizontal / left+right  (0-20)
  innerVerticalLength: number // 0v  top+bottom when 0g=true  (0-20)
  innerThickness: number // 0t  (1-6)
  innerOffset: number // 0o  (0-20)
  innerFiringError: boolean // 0f  射擊誤差
  innerFiringErrorMultiplier: number // 0e  (0-3)
  innerMovementError: boolean // 0m  移動失誤 (not shown in static preview)
  innerMovementErrorMultiplier: number // 0s  (0-3)

  // Outer lines (外側線)
  showOuterLines: boolean // 1b
  outerOpacity: number // 1a
  outerLengthNotLinked: boolean // 1g
  outerLength: number // 1l
  outerVerticalLength: number // 1v
  outerThickness: number // 1t
  outerOffset: number // 1o
  outerFiringError: boolean // 1f
  outerFiringErrorMultiplier: number // 1e  (0-3)
  outerMovementError: boolean // 1m
  outerMovementErrorMultiplier: number // 1s  (0-3)

  // Center dot (準星中心點) — square in-game
  hasDot: boolean // d
  dotThickness: number // z  (1-6)
  dotOpacity: number // a  (0-1)

  // Behavior
  overrideFiringError: boolean // m  — when true, FIXED_GAP is skipped
  overrideAllPrimary: boolean // c;1 in header — apply primary to all weapons (UI-only)

  // Sniper section (S;) — null when S; block is absent from the code
  sniper: ValorantSniperParams | null
}

export interface ValorantSniperParams {
  color: string // c / u
  hasDot: boolean // d  (default TRUE for sniper)
  dotOpacity: number // a  default 0.75
  dotThickness: number // z  default 1
}

export const SNIPER_DEFAULTS: ValorantSniperParams = {
  color: '#FF0000', // Red — idx 7, sniper default
  hasDot: true,
  dotOpacity: 0.75,
  dotThickness: 1,
}

// 8 preset colors (index 0-7); index 8 = custom (use u param)
// Verified: Red (#FF0000) = index 7 from in-game sniper UI screenshot
export const COLOR_MAP: Record<number, string> = {
  0: '#FFFFFF', // 白色  White
  1: '#00FF00', // 綠色  Green
  2: '#7FFF00', // 黃綠色 Yellow Green
  3: '#DFFF00', // 綠黃色 Green Yellow
  4: '#FFFF00', // 黃色  Yellow
  5: '#00FFFF', // 青色  Cyan
  6: '#FF00FF', // 粉紅色 Pink
  7: '#FF0000', // 紅色  Red  ← confirmed in sniper section screenshot
}

// Default values — verified against DEFAULT_PRIMARY_SETTINGS in genesy/crosshair-codes
// and cross-referenced with in-game UI (TC screenshots)
export const VALORANT_DEFAULTS: ValorantCrosshairParams = {
  color: '#FFFFFF',

  outlines: true,
  outlineThickness: 1,
  outlineOpacity: 0.5,

  showInnerLines: true,
  innerOpacity: 0.8,
  innerLengthNotLinked: false,
  innerLength: 6,
  innerVerticalLength: 6,
  innerThickness: 2,
  innerOffset: 3,
  innerFiringError: true,
  innerFiringErrorMultiplier: 1,
  innerMovementError: false,
  innerMovementErrorMultiplier: 1,

  showOuterLines: true,
  outerOpacity: 0.35,
  outerLengthNotLinked: false,
  outerLength: 2,
  outerVerticalLength: 2,
  outerThickness: 2,
  outerOffset: 10,
  outerFiringError: true, // default ON
  outerFiringErrorMultiplier: 1,
  outerMovementError: true, // default ON (outer moves with player movement by default)
  outerMovementErrorMultiplier: 1,

  hasDot: false,
  dotThickness: 2,
  dotOpacity: 1,

  overrideFiringError: false,
  overrideAllPrimary: false,

  sniper: null,
}

function fmt(n: number): string {
  return parseFloat(n.toFixed(2)).toString()
}

function kv(parts: string[], key: string, value: string | number): void {
  parts.push(key, String(value))
}

function encodeColor(parts: string[], color: string, defaultIdx: number): void {
  const presetEntry = Object.entries(COLOR_MAP).find(([, v]) => v === color)
  if (presetEntry) {
    const idx = parseInt(presetEntry[0])
    if (idx !== defaultIdx) kv(parts, 'c', idx)
  } else {
    kv(parts, 'c', 8)
    kv(parts, 'b', 1) // required by game alongside c=8 (custom color marker)
    kv(parts, 'u', color.replace('#', '').toUpperCase())
  }
}

/**
 * Encode ValorantCrosshairParams back to a profile code string.
 * Only non-default values are written, matching how the game generates codes.
 */
export function encodeValorantCrosshair(p: ValorantCrosshairParams): string {
  const D = VALORANT_DEFAULTS
  const parts: string[] = ['0']
  if (p.overrideAllPrimary) parts.push('c', '1')
  parts.push('P')

  encodeColor(parts, p.color, 0)

  if (!p.outlines) kv(parts, 'h', 0)
  if (p.outlineOpacity !== D.outlineOpacity) kv(parts, 'o', fmt(p.outlineOpacity))
  if (p.outlineThickness !== D.outlineThickness) kv(parts, 't', p.outlineThickness)

  if (p.hasDot) {
    kv(parts, 'd', 1)
    if (p.dotOpacity !== D.dotOpacity) kv(parts, 'a', fmt(p.dotOpacity))
    if (p.dotThickness !== D.dotThickness) kv(parts, 'z', p.dotThickness)
  }

  if (p.overrideFiringError) kv(parts, 'm', 1)

  // Inner lines
  if (!p.showInnerLines) kv(parts, '0b', 0)
  if (p.innerOpacity !== D.innerOpacity) kv(parts, '0a', fmt(p.innerOpacity))
  if (p.innerLengthNotLinked) kv(parts, '0g', 1)
  if (p.innerLength !== D.innerLength) kv(parts, '0l', p.innerLength)
  if (p.innerLengthNotLinked && p.innerVerticalLength !== p.innerLength)
    kv(parts, '0v', p.innerVerticalLength)
  if (p.innerThickness !== D.innerThickness) kv(parts, '0t', p.innerThickness)
  if (p.innerOffset !== D.innerOffset) kv(parts, '0o', p.innerOffset)
  if (!p.innerFiringError) kv(parts, '0f', 0)
  if (p.innerFiringError && p.innerFiringErrorMultiplier !== D.innerFiringErrorMultiplier)
    kv(parts, '0e', fmt(p.innerFiringErrorMultiplier))
  if (p.innerMovementError) kv(parts, '0m', 1)
  if (p.innerMovementError && p.innerMovementErrorMultiplier !== D.innerMovementErrorMultiplier)
    kv(parts, '0s', fmt(p.innerMovementErrorMultiplier))

  // Outer lines
  if (!p.showOuterLines) kv(parts, '1b', 0)
  if (p.outerOpacity !== D.outerOpacity) kv(parts, '1a', fmt(p.outerOpacity))
  if (p.outerLengthNotLinked) kv(parts, '1g', 1)
  if (p.outerLength !== D.outerLength) kv(parts, '1l', p.outerLength)
  if (p.outerLengthNotLinked && p.outerVerticalLength !== p.outerLength)
    kv(parts, '1v', p.outerVerticalLength)
  if (p.outerThickness !== D.outerThickness) kv(parts, '1t', p.outerThickness)
  if (p.outerOffset !== D.outerOffset) kv(parts, '1o', p.outerOffset)
  if (!p.outerFiringError) kv(parts, '1f', 0)
  if (p.outerFiringError && p.outerFiringErrorMultiplier !== D.outerFiringErrorMultiplier)
    kv(parts, '1e', fmt(p.outerFiringErrorMultiplier))
  if (!p.outerMovementError) kv(parts, '1m', 0) // outer default ON, write 0 when OFF
  if (p.outerMovementError && p.outerMovementErrorMultiplier !== D.outerMovementErrorMultiplier)
    kv(parts, '1s', fmt(p.outerMovementErrorMultiplier))

  // Sniper section
  if (p.sniper) {
    parts.push('S')
    const s = p.sniper
    encodeColor(parts, s.color, 7) // sniper default = red (idx 7)
    if (!s.hasDot) kv(parts, 'd', 0) // sniper dot default ON
    if (s.dotOpacity !== SNIPER_DEFAULTS.dotOpacity) kv(parts, 'a', fmt(s.dotOpacity))
    if (s.dotThickness !== SNIPER_DEFAULTS.dotThickness) kv(parts, 'z', s.dotThickness)
  }

  return parts.join(';')
}

/**
 * Parse consecutive key;value pairs from `parts` starting at index `from`,
 * stopping when a section marker (P, A, S, NAME) is encountered.
 * Accepting multiple stop tokens prevents ADS / Sniper params bleeding into Primary.
 */
function parseKV(parts: string[], from: number, ...stopAt: string[]): Record<string, string> {
  const stops = new Set(stopAt)
  const kv: Record<string, string> = {}
  let i = from
  while (i < parts.length && !stops.has(parts[i])) {
    if (i + 1 < parts.length) {
      kv[parts[i]] = parts[i + 1]
      i += 2
    } else break
  }
  return kv
}

function parseSniperSection(parts: string[]): ValorantSniperParams | null {
  const idx = parts.indexOf('S')
  if (idx < 0) return null

  const s = parseKV(parts, idx + 1, 'NAME')
  const colorIdx = parseInt(s['c'] ?? '7', 10)
  const color =
    colorIdx === 8 && s['u'] && s['u'].length >= 6
      ? `#${s['u'].slice(0, 6)}`
      : (COLOR_MAP[colorIdx] ?? '#FF0000')

  return {
    color,
    hasDot: s['d'] !== '0', // default TRUE for sniper (absent = on)
    dotOpacity: parseFloat(s['a'] ?? '0.75'),
    dotThickness: parseFloat(s['z'] ?? '1'),
  }
}

export function decodeValorantCrosshair(code: string): ValorantCrosshairParams {
  try {
    const parts = code.split(';')

    // Locate the Primary section marker
    let primaryStart = -1
    for (let i = 0; i < parts.length; i++) {
      if (parts[i] === 'P') {
        primaryStart = i + 1
        break
      }
    }
    if (primaryStart < 0) return VALORANT_DEFAULTS

    // c;1 in the header (before P;) = overrideAllPrimary
    let overrideAllPrimary = false
    for (let i = 0; i < primaryStart - 1; i++) {
      if (parts[i] === 'c' && parts[i + 1] === '1') {
        overrideAllPrimary = true
        break
      }
    }

    // Parse P; section only — stop before A; (ADS) or S; (Sniper)
    const p = parseKV(parts, primaryStart, 'A', 'S', 'NAME')

    const colorIdx = parseInt(p['c'] ?? '0', 10)
    const color =
      colorIdx === 8 && p['u'] && p['u'].length >= 6
        ? `#${p['u'].slice(0, 6)}`
        : (COLOR_MAP[colorIdx] ?? '#FFFFFF')

    // Boolean: "default true" params are absent when true, written as "0" when false
    const boolDefaultTrue = (key: string) => p[key] !== '0'
    // Boolean: "default false" params are absent when false, written as "1" when true
    const boolDefaultFalse = (key: string) => p[key] === '1'
    const float = (key: string, def: number) => parseFloat(p[key] ?? String(def))

    const innerLength = float('0l', 6)
    const innerLengthNotLinked = boolDefaultFalse('0g')

    const outerLength = float('1l', 2)
    const outerLengthNotLinked = boolDefaultFalse('1g')

    return {
      color,

      outlines: boolDefaultTrue('h'),
      outlineThickness: float('t', 1),
      outlineOpacity: float('o', 0.5),

      showInnerLines: boolDefaultTrue('0b'),
      innerOpacity: float('0a', 0.8),
      innerLengthNotLinked,
      innerLength,
      innerVerticalLength: innerLengthNotLinked ? float('0v', innerLength) : innerLength,
      innerThickness: float('0t', 2),
      innerOffset: float('0o', 3),
      innerFiringError: boolDefaultTrue('0f'), // default ON
      innerFiringErrorMultiplier: float('0e', 1),
      innerMovementError: boolDefaultFalse('0m'), // default OFF
      innerMovementErrorMultiplier: float('0s', 1),

      showOuterLines: boolDefaultTrue('1b'),
      outerOpacity: float('1a', 0.35),
      outerLengthNotLinked,
      outerLength,
      outerVerticalLength: outerLengthNotLinked ? float('1v', outerLength) : outerLength,
      outerThickness: float('1t', 2),
      outerOffset: float('1o', 10),
      outerFiringError: boolDefaultTrue('1f'), // default ON
      outerFiringErrorMultiplier: float('1e', 1),
      outerMovementError: boolDefaultTrue('1m'), // default ON ← outer different from inner
      outerMovementErrorMultiplier: float('1s', 1),

      hasDot: boolDefaultFalse('d'),
      dotThickness: float('z', 2),
      dotOpacity: float('a', 1),

      overrideFiringError: boolDefaultFalse('m'),
      overrideAllPrimary,

      sniper: parseSniperSection(parts),
    }
  } catch {
    return VALORANT_DEFAULTS
  }
}
