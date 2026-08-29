/**
 * Client-side mirror of the bot's `render_template` (backend
 * `twitch/utils/event_render.py`). Used only for the live preview — the bot
 * does the real render.
 *
 * 1. `[[ optional ]]` segments collapse when a `$(var)` inside has no value.
 * 2. `$(name)` / `$(@name)` substitute in a single left-to-right pass; unknown
 *    keys stay literal and a substituted value is never re-scanned.
 */
const SEGMENT_RE = /\[\[([\s\S]*?)\]\]/g
const VAR_RE = /\$\((@?\w+)\)/g

export function renderTemplate(template: string, variables: Record<string, string>): string {
  const resolved = template.replace(SEGMENT_RE, (_full, seg: string) => {
    const names = [...seg.matchAll(VAR_RE)].map(m => m[1])
    return names.some(n => !variables[n]) ? '' : seg
  })
  return resolved.replace(VAR_RE, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(variables, name) ? variables[name] : match
  )
}
