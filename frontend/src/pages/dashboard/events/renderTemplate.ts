/**
 * Client-side mirror of the bot's `render_template` (backend
 * `twitch/utils/event_render.py`). Single left-to-right pass: unknown
 * placeholders are left as-is, and `$(...)` inside a substituted value is never
 * re-expanded. Used only for the live preview — the bot does the real render.
 */
const VAR_RE = /\$\((\w+)\)/g

export function renderTemplate(template: string, variables: Record<string, string>): string {
  return template.replace(VAR_RE, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(variables, name) ? variables[name] : match
  )
}
