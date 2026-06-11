// Build-time deployment target ('production' | 'staging'), mirroring the backend
// ENVIRONMENT. Set per Cloudflare Pages environment; unset in local dev.
export const APP_ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT ?? ''

// WIP locks show in production only; staging and dev stay unlocked for testing.
// Fail-safe: any non-staging prod build keeps the lock, so a missing
// VITE_ENVIRONMENT can never expose WIP pages — staging must opt out explicitly.
export const SHOW_WIP_LOCK = import.meta.env.PROD && APP_ENVIRONMENT !== 'staging'
