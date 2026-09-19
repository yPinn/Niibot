import { LockOverlay } from './LockOverlay'

interface AffiliateLockOverlayProps {
  message: string
  /** Set when the overlay sits at PageMain level (not inside a bounded Card) so it stays click-blocking through scroll. */
  fullPage?: boolean
  /** Set for small containers that can't fit the standard card — see LockOverlay. */
  compact?: boolean
  className?: string
}

export function AffiliateLockOverlay({
  message,
  fullPage,
  compact,
  className,
}: AffiliateLockOverlayProps) {
  return (
    <LockOverlay
      icon="fa-solid fa-lock"
      title="需要實況盟友資格"
      description={message}
      fullPage={fullPage}
      compact={compact}
      className={className}
    />
  )
}
