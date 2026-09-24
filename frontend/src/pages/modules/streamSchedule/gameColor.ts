import { useEffect, useState } from 'react'

import { searchStreamScheduleGames } from '@/api/streamSchedule'

// Fixed vibrancy regardless of the source artwork — box art averages out
// muddy/desaturated more often than not, and the whole point here is a
// punchy, always-legible block, not a literal average. Only the hue comes
// from the actual box art; saturation/lightness are held constant so text
// contrast never has to be computed per-game.
const SAMPLE_SIZE = 16
const SATURATION = 0.6
const LIGHTNESS = 0.38

const colorCache = new Map<string, string | null>()

function rgbToHue(r: number, g: number, b: number): number {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const d = max - min
  if (d === 0) return 0
  let h: number
  switch (max) {
    case r:
      h = ((g - b) / d) % 6
      break
    case g:
      h = (b - r) / d + 2
      break
    default:
      h = (r - g) / d + 4
  }
  h *= 60
  return h < 0 ? h + 360 : h
}

function hsl(h: number, s: number, l: number): string {
  return `hsl(${h.toFixed(1)} ${(s * 100).toFixed(0)}% ${(l * 100).toFixed(0)}%)`
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`failed to load ${url}`))
    img.src = url
  })
}

/** Twitch box art URLs are a template the caller fills in, not a ready image
 * URL — same convention GamePicker already uses for the same endpoint. */
function thumbnailUrl(template: string, width: number, height: number): string {
  return template.replace('{width}', String(width)).replace('{height}', String(height))
}

function extractHue(img: HTMLImageElement): number | null {
  const canvas = document.createElement('canvas')
  canvas.width = SAMPLE_SIZE
  canvas.height = SAMPLE_SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(img, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
  // Throws if the canvas got tainted (e.g. the CDN ever drops its CORS
  // header) — caught by the caller, falls back to the flat kind-based color.
  const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE)
  let r = 0
  let g = 0
  let b = 0
  let n = 0
  for (let i = 0; i < data.length; i += 4) {
    r += data[i]
    g += data[i + 1]
    b += data[i + 2]
    n++
  }
  if (n === 0) return null
  return rgbToHue(r / n, g / n, b / n)
}

async function computeGameColor(gameId: string, gameName: string): Promise<string | null> {
  try {
    const matches = await searchStreamScheduleGames(gameName)
    const match = matches.find(m => m.id === gameId)
    if (!match?.box_art_url) return null
    const img = await loadImage(thumbnailUrl(match.box_art_url, 32, 43))
    const hue = extractHue(img)
    if (hue === null) return null
    return `linear-gradient(to bottom, ${hsl(hue, SATURATION, LIGHTNESS)}, black)`
  } catch {
    return null
  }
}

/** A game's box-art-derived background gradient (its main hue fading to
 * black), cached by game id for the session — the same game reused across
 * multiple schedules (a weekly show, say) only ever gets fetched and
 * computed once. Returns null while loading, on failure, or when there's no
 * game to color; callers fall back to the kind-based color.
 *
 * Reads the cache directly on every render rather than syncing it into
 * state — a cache hit needs no effect at all this way, only a cache miss
 * does (to kick off the fetch and force a re-render once it resolves). */
export function useGameColor(gameId: string | null, gameName: string | null): string | null {
  const [, forceRender] = useState(0)

  useEffect(() => {
    if (!gameId || !gameName || colorCache.has(gameId)) return
    let cancelled = false
    computeGameColor(gameId, gameName).then(result => {
      colorCache.set(gameId, result)
      if (!cancelled) forceRender(n => n + 1)
    })
    return () => {
      cancelled = true
    }
  }, [gameId, gameName])

  return gameId ? (colorCache.get(gameId) ?? null) : null
}
