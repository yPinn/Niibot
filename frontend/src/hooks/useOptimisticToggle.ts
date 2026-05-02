import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'

export interface UseOptimisticToggleOptions<T extends { enabled: boolean }> {
  /** The React state setter for the list that contains the toggled item. */
  setState: React.Dispatch<React.SetStateAction<T[]>>
  /** Returns a unique key for each item (e.g. command_name, timer_name). */
  getId: (item: T) => string | number
  /** The async API call that performs the toggle. */
  toggleFn: (item: T, newEnabled: boolean) => Promise<void>
  /** Toast message overrides. */
  messages?: {
    on?: string
    off?: string
    error?: string
  }
}

/**
 * Returns a `toggle` function that:
 * 1. Immediately flips the item's `enabled` field in state (optimistic update).
 * 2. Calls the API; reverts the optimistic update on failure.
 *
 * Usage:
 *   const { toggle } = useOptimisticToggle({
 *     setState: setTimers,
 *     getId: t => t.timer_name,
 *     toggleFn: (t, enabled) => toggleTimer(t.timer_name, enabled),
 *     messages: { on: '計時器已啟用', off: '計時器已停用', error: '切換計時器狀態失敗' },
 *   })
 */
export function useOptimisticToggle<T extends { enabled: boolean }>(
  options: UseOptimisticToggleOptions<T>
): { toggle: (item: T) => Promise<void> } {
  const { setState, getId, toggleFn, messages } = options
  const pendingRef = useRef(new Set<string | number>())
  const messagesRef = useRef(messages)
  useEffect(() => {
    messagesRef.current = messages
  })

  const toggle = useCallback(
    async (item: T) => {
      const id = getId(item)
      const newEnabled = !item.enabled

      if (pendingRef.current.has(id)) return
      pendingRef.current.add(id)

      setState(prev => prev.map(x => (getId(x) === id ? { ...x, enabled: newEnabled } : x)))

      try {
        await toggleFn(item, newEnabled)
        const msgs = messagesRef.current
        toast.success(newEnabled ? (msgs?.on ?? '已啟用') : (msgs?.off ?? '已停用'))
      } catch {
        setState(prev => prev.map(x => (getId(x) === id ? { ...x, enabled: item.enabled } : x)))
        toast.error(messagesRef.current?.error ?? '切換失敗')
      } finally {
        pendingRef.current.delete(id)
      }
    },
    [setState, getId, toggleFn]
  )

  return { toggle }
}
