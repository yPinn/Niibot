const TEST_ORIGIN = 'https://niibot.test'

/** Resolve either browser-relative or deployment-absolute fetch inputs in API tests. */
export function requestUrl(input: unknown): URL {
  const value = input instanceof Request ? input.url : String(input)
  return new URL(value, TEST_ORIGIN)
}
