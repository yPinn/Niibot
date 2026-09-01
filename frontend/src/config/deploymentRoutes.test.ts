import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('Cloudflare Pages function routes', () => {
  it('routes API proxies and dynamic social metadata through Pages Functions', () => {
    const routesPath = path.resolve(import.meta.dirname, '../../public/_routes.json')

    expect(existsSync(routesPath)).toBe(true)
    if (!existsSync(routesPath)) return

    const routes = JSON.parse(readFileSync(routesPath, 'utf8')) as {
      version: number
      include: string[]
      exclude: string[]
    }

    expect(routes).toEqual({
      version: 1,
      include: ['/api/*', '/health', '/status', '/donate/*', '/*/commands', '/*/crosshairs'],
      exclude: [],
    })
  })
})
