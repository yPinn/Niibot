/** "Later" on the mod setup prompt holds for the browser session, so the
 * Overview stops re-opening it on every visit but reminds again next session.
 * Storage can be unavailable (private mode, blocked site data); then the
 * prompt simply shows as before. */
const KEY = 'niibot:mod-prompt-dismissed'

export function isModPromptDismissed(): boolean {
  try {
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function dismissModPrompt(): void {
  try {
    sessionStorage.setItem(KEY, '1')
  } catch {
    // Not persisted; the prompt shows again on the next visit.
  }
}

/** Hash that opens Get Started's manual mod steps. */
export const MANUAL_MOD_HASH = 'manual-mod'
