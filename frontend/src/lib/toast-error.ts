/**
 * The single way to show an error to the user.
 *
 * Disclosure is deliberately minimal — the users are non-technical:
 *   - 4xx  → one polished sentence. No code, no status, nothing to copy;
 *            these are things the user can fix themselves.
 *   - 5xx / network → the sentence plus a "回報問題" action. The action copies
 *            a short reference (request id + page) to the clipboard so support
 *            can trace it. The id is never shown inline.
 */

import { toast } from 'sonner'

import { ApiError, errorMessage } from '@/api/errors'

export function toastApiError(e: unknown, fallback: string): void {
  const err = e instanceof ApiError ? e : null
  const message = err ? err.message : errorMessage(e, fallback)

  if (!err || !err.isReportable) {
    toast.error(message)
    return
  }

  const ref = err.requestId ?? `${new Date().toISOString()}`
  toast.error(message, {
    description: '如果狀況持續，可以把問題回報給開發者',
    action: {
      label: '回報問題',
      onClick: () => {
        const path = typeof window !== 'undefined' ? window.location.pathname : ''
        const payload = `錯誤參考碼：${ref}\n頁面：${path}`
        void navigator.clipboard
          ?.writeText(payload)
          .then(() => toast.success('已複製，把它貼給開發者就行'))
          .catch(() => toast.message(payload))
      },
    },
  })
}
