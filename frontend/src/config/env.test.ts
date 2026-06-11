import { afterEach, describe, expect, it, vi } from 'vitest'

// env.ts reads import.meta.env at module-eval time, so each case stubs the
// env then re-imports the module via vi.resetModules to pick up fresh values.
async function loadEnv(stub: { PROD?: boolean; VITE_ENVIRONMENT?: string }) {
  vi.resetModules()
  if (stub.PROD !== undefined) vi.stubEnv('PROD', stub.PROD)
  if (stub.VITE_ENVIRONMENT !== undefined) vi.stubEnv('VITE_ENVIRONMENT', stub.VITE_ENVIRONMENT)
  return import('@/config/env')
}

describe('SHOW_WIP_LOCK', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('is true for a production build (locked)', async () => {
    const { SHOW_WIP_LOCK } = await loadEnv({ PROD: true, VITE_ENVIRONMENT: 'production' })
    expect(SHOW_WIP_LOCK).toBe(true)
  })

  it('is true for a production build with no VITE_ENVIRONMENT (fail-safe)', async () => {
    const { SHOW_WIP_LOCK } = await loadEnv({ PROD: true, VITE_ENVIRONMENT: '' })
    expect(SHOW_WIP_LOCK).toBe(true)
  })

  it('is false for a staging build (unlocked)', async () => {
    const { SHOW_WIP_LOCK } = await loadEnv({ PROD: true, VITE_ENVIRONMENT: 'staging' })
    expect(SHOW_WIP_LOCK).toBe(false)
  })

  it('is false in local dev (not a production build)', async () => {
    const { SHOW_WIP_LOCK } = await loadEnv({ PROD: false, VITE_ENVIRONMENT: '' })
    expect(SHOW_WIP_LOCK).toBe(false)
  })
})
