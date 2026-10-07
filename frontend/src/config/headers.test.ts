import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Guards public/_headers (Cloudflare Pages). Its rules silently match nothing
// when malformed — the file once shipped `/\*` paths and so sent no CSP at all.

interface Rule {
  path: string
  set: Map<string, string>
  detach: Set<string>
}

function parseHeaders(text: string): Rule[] {
  const rules: Rule[] = []
  for (const raw of text.split(/\r?\n/)) {
    if (!raw.trim() || raw.startsWith('#')) continue
    if (raw.startsWith('/')) {
      rules.push({ path: raw.trim(), set: new Map(), detach: new Set() })
      continue
    }
    const rule = rules.at(-1)
    if (!rule) throw new Error(`header before any path: ${raw}`)
    if (raw.startsWith('!')) {
      rule.detach.add(raw.slice(1).trim())
      continue
    }
    const sep = raw.indexOf(':')
    rule.set.set(raw.slice(0, sep).trim(), raw.slice(sep + 1).trim())
  }
  return rules
}

const text = readFileSync(resolve(import.meta.dirname, '../../public/_headers'), 'utf8')
const rules = parseHeaders(text)
const rule = (path: string) => {
  const found = rules.find(r => r.path === path)
  if (!found) throw new Error(`no rule for ${path}`)
  return found
}
const directive = (csp: string | undefined, name: string) =>
  (csp ?? '')
    .split(';')
    .map(d => d.trim().split(/\s+/))
    .find(([n]) => n === name)
    ?.slice(1) ?? []

const CSP = 'Content-Security-Policy'
const CSP_RO = 'Content-Security-Policy-Report-Only'
const VQ_OVERLAY = '/*/video-queue/overlay'

describe('public/_headers', () => {
  it('has no escaped characters (a Markdown formatter once wrote `/\\*`)', () => {
    expect(text).not.toContain('\\')
  })

  it('keeps every header line at column 0 (indented lines are ignored)', () => {
    for (const line of text.split(/\r?\n/)) expect(line).not.toMatch(/^\s+\S/)
  })

  it('has the global rule plus the overlay rules', () => {
    expect(rules.map(r => r.path)).toEqual(
      expect.arrayContaining(['/*', '/live-display', VQ_OVERLAY, '/*/game-queue/overlay'])
    )
  })

  it('detaches the global CSP wherever a path brings its own', () => {
    const globalCsp = rule('/*').set.has(CSP) ? CSP : CSP_RO
    for (const r of rules.filter(r => r.path !== '/*' && (r.set.has(CSP) || r.set.has(CSP_RO)))) {
      expect(r.detach, r.path).toContain(globalCsp)
      // `!` also drops the rule's own header of that name.
      expect(r.set.has(globalCsp), r.path).toBe(false)
    }
  })

  it('lets every overlay be framed (OBS, dashboard preview)', () => {
    for (const path of ['/live-display', VQ_OVERLAY, '/*/game-queue/overlay']) {
      expect(rule(path).detach, path).toContain('X-Frame-Options')
      expect(directive(rule(path).set.get(CSP), 'frame-ancestors'), path).toEqual(['*'])
    }
  })

  it('allows what the video-queue overlay HLS player needs', () => {
    const csp = rule(VQ_OVERLAY).set.get(CSP)
    expect(directive(csp, 'media-src')).toContain('blob:')
    expect(directive(csp, 'connect-src')).toEqual(
      expect.arrayContaining([
        'https://*.ttvnw.net',
        // API_DIRECT_URL — variant playlists (docs/guides/cloudflare-pages.md)
        'https://niibot-api.llazypilot.com',
        'https://niibot-api-staging.llazypilot.com',
      ])
    )
  })

  it("allows index.html's inline scripts in every script-src (every route serves it)", () => {
    const html = readFileSync(resolve(import.meta.dirname, '../../index.html'), 'utf8')
    // Executable inline scripts only: no src, and not a data block like JSON-LD.
    const inline = [...html.matchAll(/<script(?![^>]*\b(?:src|type)=)[^>]*>([\s\S]*?)<\/script>/g)]
    expect(inline.length).toBeGreaterThan(0)
    const hashes = inline.map(
      ([, body]) => `'sha256-${createHash('sha256').update(body).digest('base64')}'`
    )
    for (const r of rules) {
      for (const name of [CSP, CSP_RO]) {
        const csp = r.set.get(name)
        if (csp)
          expect(directive(csp, 'script-src'), `${r.path} ${name}`).toEqual(
            expect.arrayContaining(hashes)
          )
      }
    }
  })
})
