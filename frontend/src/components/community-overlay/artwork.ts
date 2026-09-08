export function resolveSameOriginArtwork(value: string | null, origin?: string): string | null {
  if (!value) return null
  if (!/^\/images\/collections\/[A-Za-z0-9][A-Za-z0-9._/-]*\.(?:jpe?g|png|webp)$/i.test(value)) {
    return null
  }
  if (value.includes('..') || value.includes('//')) return null
  const baseOrigin =
    origin ?? (typeof window === 'undefined' ? 'https://niibot.invalid' : window.location.origin)
  try {
    const expectedOrigin = new URL(baseOrigin).origin
    const url = new URL(value, baseOrigin)
    if (
      (url.protocol !== 'http:' && url.protocol !== 'https:') ||
      url.origin !== expectedOrigin ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== value ||
      !url.pathname.startsWith('/images/collections/')
    ) {
      return null
    }
    return value
  } catch {
    return null
  }
}
