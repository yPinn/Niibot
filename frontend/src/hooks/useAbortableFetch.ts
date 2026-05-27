import { useCallback, useEffect, useRef } from 'react'

/**
 * Returns a `guard` function. Wrap any setState/dispatch call with it:
 *   guard(() => setState(data))
 * The callback is skipped if the component has unmounted since the fetch started.
 *
 * Also returns `newToken()` — call it at the start of each fetch to invalidate
 * any earlier in-flight callbacks (prevents out-of-order updates on rapid triggers).
 */
export function useAbortableFetch() {
  const mountedRef = useRef(true)
  const tokenRef = useRef(0)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const newToken = useCallback(() => {
    tokenRef.current += 1
    return tokenRef.current
  }, [])

  const guard = useCallback((token: number, fn: () => void) => {
    if (mountedRef.current && token === tokenRef.current) fn()
  }, [])

  return { guard, newToken }
}
