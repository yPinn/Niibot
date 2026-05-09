export interface ValorantCrosshairParams {
  color: string
  lineLength: number
  gap: number
  thickness: number
  opacity: number
  hasDot: boolean
  dotSize: number
  outerLinesEnabled: boolean
  outerLength: number
  outerGap: number
  outerThickness: number
  outerOpacity: number
}

const COLOR_MAP: Record<number, string> = {
  0: '#FFFFFF',
  1: '#00FF00',
  2: '#FFFF00',
  3: '#00FFFF',
  4: '#FF4444',
  6: '#FF69B4',
}

export const VALORANT_DEFAULTS: ValorantCrosshairParams = {
  color: '#FFFFFF',
  lineLength: 4,
  gap: 2,
  thickness: 2,
  opacity: 1,
  hasDot: false,
  dotSize: 2,
  outerLinesEnabled: false,
  outerLength: 2,
  outerGap: 10,
  outerThickness: 2,
  outerOpacity: 0.35,
}

function parseKV(parts: string[], from: number, until: string): Record<string, string> {
  const kv: Record<string, string> = {}
  let i = from
  while (i < parts.length && parts[i] !== until) {
    if (i + 1 < parts.length) {
      kv[parts[i]] = parts[i + 1]
      i += 2
    } else break
  }
  return kv
}

export function decodeValorantCrosshair(code: string): ValorantCrosshairParams {
  try {
    const parts = code.split(';')

    // Locate primary section marker
    let primaryStart = -1
    for (let i = 0; i < parts.length; i++) {
      if (parts[i] === 'P') {
        primaryStart = i + 1
        break
      }
    }
    if (primaryStart < 0) return VALORANT_DEFAULTS

    const p = parseKV(parts, primaryStart, 'S')

    // Color
    const colorIdx = parseInt(p['c'] ?? '0', 10)
    let color: string
    if (colorIdx === 5 && p['u'] && p['u'].length >= 6) {
      color = `#${p['u'].slice(0, 6)}`
    } else {
      color = COLOR_MAP[colorIdx] ?? '#FFFFFF'
    }

    return {
      color,
      lineLength: parseFloat(p['0l'] ?? '4'),
      gap: parseFloat(p['0o'] ?? '2'),
      thickness: parseFloat(p['0t'] ?? '2'),
      opacity: parseFloat(p['0a'] ?? '1'),
      hasDot: p['d'] === '1',
      dotSize: parseFloat(p['z'] ?? '2'),
      outerLinesEnabled: p['1b'] === '1',
      outerLength: parseFloat(p['1l'] ?? '2'),
      outerGap: parseFloat(p['1o'] ?? '10'),
      outerThickness: parseFloat(p['1t'] ?? '2'),
      outerOpacity: parseFloat(p['1a'] ?? '0.35'),
    }
  } catch {
    return VALORANT_DEFAULTS
  }
}
