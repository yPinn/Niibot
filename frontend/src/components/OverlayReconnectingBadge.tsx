import styles from './OverlayReconnectingBadge.module.css'

/**
 * Small "reconnecting…" indicator shared by the OBS-facing overlay pages
 * (VideoQueueOverlay, CommunityOverlay, GameQueueOverlay). Deliberately
 * self-styled rather than matching each overlay's own branded look — this
 * only ever renders in `?preview=1` mode, so a real viewer never sees it.
 *
 * Requires a positioned ancestor (`position: relative | fixed | absolute`)
 * to anchor to — every overlay page's root element already is one.
 */
export function OverlayReconnectingBadge({ visible }: { visible: boolean }) {
  if (!visible) return null
  return <div className={styles.badge}>重新連線中…</div>
}
