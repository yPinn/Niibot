import { useEffect, useRef } from 'react'

export interface UsePollingOptions {
  /** Called immediately and then on each interval tick. */
  fetchFn: () => Promise<void>
  /** Polling interval in milliseconds. */
  intervalMs: number
  /**
   * When false the polling does not start (and an existing interval is cleared).
   * Defaults to true.
   */
  enabled?: boolean
  /**
   * When true, skips the immediate call on mount and only runs on interval ticks.
   * Use when a separate effect already handles the initial fetch.
   * Defaults to false.
   */
  skipInitialCall?: boolean
}

/**
 * Starts a polling loop: calls `fetchFn` immediately, then every `intervalMs` ms.
 * Cleans up automatically on unmount or when `enabled` becomes false.
 *
 * `fetchFn` is stored in a ref so the interval always calls the latest version
 * without causing the interval to restart on every render.
 *
 * Usage:
 *   usePolling({ fetchFn: fetchState, intervalMs: 5_000, enabled: !!username })
 */
export function usePolling({
  fetchFn,
  intervalMs,
  enabled = true,
  skipInitialCall = false,
}: UsePollingOptions): void {
  // Always hold the latest fetchFn without recreating the interval.
  const fetchRef = useRef(fetchFn)
  useEffect(() => {
    fetchRef.current = fetchFn
  })

  useEffect(() => {
    if (!enabled) return

    const run = () => fetchRef.current()
    if (!skipInitialCall) run()
    const id = setInterval(run, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, enabled, skipInitialCall])
}
